"""Tests for API endpoints."""

import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.encryption import encrypt
from app.models import Account, Credential, SyncLog, Transaction


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        """Health endpoint returns ok status."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["account_count"] == 0
        assert data["last_sync_at"] is None

    @pytest.mark.asyncio
    async def test_health_shows_last_sync(self, client, db):
        """Health endpoint shows last sync info."""
        sync_log = SyncLog(
            started_at=int(time.time()),
            completed_at=int(time.time()),
            status="success",
            accounts_synced=2,
            transactions_added=10,
        )
        db.add(sync_log)
        await db.commit()

        response = await client.get("/health")
        data = response.json()
        assert data["last_sync_status"] == "success"
        assert data["last_sync_at"] is not None


class TestAccountsEndpoint:
    @pytest.mark.asyncio
    async def test_list_accounts_empty(self, client):
        """List accounts returns empty list when none exist."""
        response = await client.get("/accounts/")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_accounts(self, client, db):
        """List accounts returns all accounts."""
        account = Account(
            id="act_1",
            provider="plaid",
            org_domain=None,
            org_name="Chase",
            name="Chase Checking",
            balance_current=123456,
        )
        db.add(account)
        await db.commit()

        response = await client.get("/accounts/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "act_1"
        assert data[0]["name"] == "Chase Checking"

    @pytest.mark.asyncio
    async def test_list_accounts_pagination(self, client, db):
        """List accounts supports limit and offset."""
        for i in range(5):
            db.add(Account(
                id=f"act_{i}",
                provider="plaid",
                org_domain=None,
                name=f"Account {i}",
            ))
        await db.commit()

        # Default returns all
        response = await client.get("/accounts/")
        assert len(response.json()) == 5

        # With limit
        response = await client.get("/accounts/", params={"limit": 2})
        assert len(response.json()) == 2

        # With offset
        response = await client.get("/accounts/", params={"limit": 2, "offset": 3})
        assert len(response.json()) == 2

    @pytest.mark.asyncio
    async def test_get_account(self, client, db):
        """Get specific account by ID."""
        account = Account(
            id="act_1",
            provider="plaid",
            org_domain=None,
            name="Chase Checking",
        )
        db.add(account)
        await db.commit()

        response = await client.get("/accounts/act_1")
        assert response.status_code == 200
        assert response.json()["id"] == "act_1"

    @pytest.mark.asyncio
    async def test_get_account_not_found(self, client):
        """Get nonexistent account returns 404."""
        response = await client.get("/accounts/nonexistent")
        assert response.status_code == 404


class TestTransactionsEndpoint:
    @pytest.mark.asyncio
    async def test_list_transactions(self, client, db):
        """List transactions with filters."""
        account = Account(
            id="act_1",
            provider="plaid",
            org_domain=None,
            name="Test Account",
        )
        db.add(account)

        now = int(time.time())
        tx1 = Transaction(
            account_id="act_1",
            external_id="tx_1",
            posted_at=now,
            amount=-5000,
            description="Coffee",
            category="Food",
        )
        tx2 = Transaction(
            account_id="act_1",
            external_id="tx_2",
            posted_at=now - 86400,
            amount=-10000,
            description="Groceries",
            category="Shopping",
        )
        db.add_all([tx1, tx2])
        await db.commit()

        # List all
        response = await client.get("/transactions/")
        assert response.status_code == 200
        assert len(response.json()) == 2

        # Filter by category
        response = await client.get("/transactions/", params={"category": "Food"})
        assert len(response.json()) == 1
        assert response.json()[0]["description"] == "Coffee"

        # Filter by account
        response = await client.get("/transactions/", params={"account_id": "act_1"})
        assert len(response.json()) == 2

    @pytest.mark.asyncio
    async def test_search_transactions(self, client, db):
        """Search transactions by description."""
        account = Account(
            id="act_1",
            provider="plaid",
            org_domain=None,
            name="Test Account",
        )
        db.add(account)

        now = int(time.time())
        db.add_all([
            Transaction(
                account_id="act_1", external_id="tx_1",
                posted_at=now, amount=-5000, description="Starbucks Coffee",
            ),
            Transaction(
                account_id="act_1", external_id="tx_2",
                posted_at=now, amount=-10000, description="Amazon Purchase",
            ),
            Transaction(
                account_id="act_1", external_id="tx_3",
                posted_at=now, amount=-3000, description="Coffee Bean & Tea",
            ),
        ])
        await db.commit()

        # Search for "coffee" (case insensitive)
        response = await client.get("/transactions/", params={"search": "coffee"})
        assert response.status_code == 200
        assert len(response.json()) == 2

        # Search for "amazon"
        response = await client.get("/transactions/", params={"search": "amazon"})
        assert len(response.json()) == 1

        # No results
        response = await client.get("/transactions/", params={"search": "walmart"})
        assert len(response.json()) == 0

    @pytest.mark.asyncio
    async def test_update_transaction(self, client, db):
        """Update transaction category and notes."""
        account = Account(
            id="act_1",
            provider="plaid",
            org_domain=None,
            name="Test Account",
        )
        db.add(account)

        tx = Transaction(
            account_id="act_1",
            external_id="tx_1",
            posted_at=int(time.time()),
            amount=-5000,
            description="Coffee",
        )
        db.add(tx)
        await db.commit()

        response = await client.patch(
            f"/transactions/{tx.id}",
            json={"category": "Food & Dining", "notes": "Morning coffee"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "Food & Dining"
        assert data["notes"] == "Morning coffee"


class TestSyncEndpoints:
    @pytest.mark.asyncio
    async def test_sandbox_token_creates_credentials(self, client, db):
        """POST /sync/sandbox-token creates credentials via mock PlaidClient."""
        with patch("app.routes.sync.PlaidClient") as MockPlaidClient:
            mock_client = MockPlaidClient.return_value
            mock_client.create_sandbox_public_token = AsyncMock(return_value="public-sandbox-token")
            mock_client.exchange_public_token = AsyncMock(return_value=("access-sandbox-123", "item-123"))

            response = await client.post("/sync/sandbox-token")

        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "plaid"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_exchange_token_creates_credentials(self, client, db):
        """POST /sync/credentials exchanges public token for access credentials."""
        with patch("app.routes.sync.PlaidClient") as MockPlaidClient:
            mock_client = MockPlaidClient.return_value
            mock_client.exchange_public_token = AsyncMock(return_value=("access-test-123", "item-test-123"))

            response = await client.post(
                "/sync/credentials",
                json={"public_token": "public-test-token"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "plaid"

    @pytest.mark.asyncio
    async def test_exchange_token_rejects_duplicate(self, client, db):
        """POST /sync/credentials rejects when credentials already exist."""
        # Create existing credential
        cred = Credential(
            id="cred_1",
            provider="plaid",
            encrypted_data=encrypt(json.dumps({"access_token": "test", "item_id": "test"})),
        )
        db.add(cred)
        await db.commit()

        response = await client.post(
            "/sync/credentials",
            json={"public_token": "public-test-token"},
        )
        assert response.status_code == 400
        assert "already configured" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_trigger_sync(self, client, db):
        """POST /sync/ triggers sync and returns SyncLog."""
        with patch("app.routes.sync.sync_accounts") as mock_sync:
            sync_log = SyncLog(
                started_at=int(time.time()),
                completed_at=int(time.time()),
                status="success",
                accounts_synced=2,
                transactions_added=10,
                transactions_updated=0,
            )
            db.add(sync_log)
            await db.flush()
            mock_sync.return_value = sync_log

            response = await client.post("/sync/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["accounts_synced"] == 2
        assert data["transactions_added"] == 10

    @pytest.mark.asyncio
    async def test_trigger_sync_409_when_already_running(self, client, db):
        """POST /sync/ returns 409 when sync already in progress."""
        with patch("app.routes.sync.sync_accounts") as mock_sync:
            mock_sync.side_effect = RuntimeError("Sync already in progress")

            response = await client.post("/sync/")

        assert response.status_code == 409
        assert "already in progress" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_credentials(self, client, db):
        """DELETE /sync/credentials deletes stored credentials."""
        cred = Credential(
            id="cred_1",
            provider="plaid",
            encrypted_data=encrypt(json.dumps({"access_token": "test", "item_id": "test"})),
        )
        db.add(cred)
        await db.commit()

        response = await client.delete("/sync/credentials")
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_credentials_404_when_none(self, client):
        """DELETE /sync/credentials returns 404 when no credentials exist."""
        response = await client.delete("/sync/credentials")
        assert response.status_code == 404


class TestAnalyticsEndpoint:
    @pytest.mark.asyncio
    async def test_spending_by_category(self, client, db):
        """Get spending grouped by category."""
        account = Account(
            id="act_1",
            provider="plaid",
            org_domain=None,
            name="Test Account",
        )
        db.add(account)

        now = int(time.time())
        transactions = [
            Transaction(
                account_id="act_1",
                external_id="tx_1",
                posted_at=now,
                amount=-5000,
                description="Coffee",
                category="Food",
            ),
            Transaction(
                account_id="act_1",
                external_id="tx_2",
                posted_at=now,
                amount=-3000,
                description="Lunch",
                category="Food",
            ),
            Transaction(
                account_id="act_1",
                external_id="tx_3",
                posted_at=now,
                amount=-10000,
                description="Gas",
                category="Transportation",
            ),
            Transaction(
                account_id="act_1",
                external_id="tx_4",
                posted_at=now,
                amount=100000,  # Income - should be excluded
                description="Paycheck",
                category="Income",
            ),
        ]
        db.add_all(transactions)
        await db.commit()

        response = await client.get("/analytics/spending-by-category")
        assert response.status_code == 200
        data = response.json()

        # Should only include expenses (negative amounts)
        categories = {c["category"]: c for c in data["categories"]}
        assert "Food" in categories
        assert categories["Food"]["total"] == 8000  # 50 + 30 = 80 dollars
        assert categories["Food"]["count"] == 2
        assert "Transportation" in categories
        assert categories["Transportation"]["total"] == 10000
        assert "Income" not in categories  # Positive amount excluded
