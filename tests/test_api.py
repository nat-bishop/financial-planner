"""Tests for API endpoints."""

import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.core.encryption import encrypt
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
        assert "providers" in data

    @pytest.mark.asyncio
    async def test_health_shows_last_sync(self, client, db):
        """Health endpoint shows last sync info."""
        sync_log = SyncLog(
            provider="simplefin",
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

    @pytest.mark.asyncio
    async def test_health_shows_provider_status(self, client, db):
        """Health endpoint includes per-provider status."""
        response = await client.get("/health")
        data = response.json()
        # Should have at least simplefin provider
        assert len(data["providers"]) >= 1
        simplefin = next(p for p in data["providers"] if p["provider"] == "simplefin")
        assert simplefin["connected"] is False
        assert simplefin["display_name"] == "SimpleFIN Bridge"


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
            provider="simplefin",
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
                provider="simplefin",
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
    async def test_list_accounts_excludes_disabled(self, client, db):
        """Disabled accounts are excluded from list by default."""
        db.add(Account(id="act_1", provider="simplefin", name="Visible"))
        db.add(Account(id="act_2", provider="simplefin", name="Hidden", is_disabled=True))
        await db.commit()

        response = await client.get("/accounts/")
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "act_1"

    @pytest.mark.asyncio
    async def test_list_accounts_include_disabled(self, client, db):
        """include_disabled=true returns all accounts including disabled."""
        db.add(Account(id="act_1", provider="simplefin", name="Visible"))
        db.add(Account(id="act_2", provider="simplefin", name="Hidden", is_disabled=True))
        await db.commit()

        response = await client.get("/accounts/", params={"include_disabled": "true"})
        data = response.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_toggle_account_disabled(self, client, db):
        """PATCH /accounts/{id} toggles disabled state."""
        db.add(Account(id="act_1", provider="simplefin", name="Test"))
        await db.commit()

        # Disable
        response = await client.patch("/accounts/act_1", json={"is_disabled": True})
        assert response.status_code == 200
        assert response.json()["is_disabled"] is True

        # Re-enable
        response = await client.patch("/accounts/act_1", json={"is_disabled": False})
        assert response.status_code == 200
        assert response.json()["is_disabled"] is False


class TestTransactionsEndpoint:
    @pytest.mark.asyncio
    async def test_list_transactions(self, client, db):
        """List transactions with filters."""
        account = Account(
            id="act_1",
            provider="simplefin",
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
        assert len(response.json()["transactions"]) == 2

        # Filter by category
        response = await client.get("/transactions/", params={"category": "Food"})
        assert len(response.json()["transactions"]) == 1
        assert response.json()["transactions"][0]["description"] == "Coffee"

        # Filter by account
        response = await client.get("/transactions/", params={"account_id": "act_1"})
        assert len(response.json()["transactions"]) == 2

    @pytest.mark.asyncio
    async def test_search_transactions(self, client, db):
        """Search transactions by description."""
        account = Account(
            id="act_1",
            provider="simplefin",
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
        assert len(response.json()["transactions"]) == 2

        # Search for "amazon"
        response = await client.get("/transactions/", params={"search": "amazon"})
        assert len(response.json()["transactions"]) == 1

        # No results
        response = await client.get("/transactions/", params={"search": "walmart"})
        assert len(response.json()["transactions"]) == 0

    @pytest.mark.asyncio
    async def test_update_transaction(self, client, db):
        """Update transaction category and notes."""
        account = Account(
            id="act_1",
            provider="simplefin",
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

    @pytest.mark.asyncio
    async def test_transactions_exclude_disabled_accounts(self, client, db):
        """Transactions from disabled accounts are excluded."""
        db.add(Account(id="act_1", provider="simplefin", name="Visible"))
        db.add(Account(id="act_2", provider="simplefin", name="Hidden", is_disabled=True))
        now = int(time.time())
        db.add(Transaction(
            account_id="act_1", external_id="tx1",
            posted_at=now, amount=-100, description="Visible",
        ))
        db.add(Transaction(
            account_id="act_2", external_id="tx2",
            posted_at=now, amount=-200, description="Hidden",
        ))
        await db.commit()

        response = await client.get("/transactions/")
        data = response.json()["transactions"]
        assert len(data) == 1
        assert data[0]["description"] == "Visible"

    @pytest.mark.asyncio
    async def test_transaction_default_category(self, client, db):
        """Transactions default to 'Uncategorized' category."""
        db.add(Account(id="act_1", provider="simplefin", name="Test"))
        db.add(Transaction(
            account_id="act_1", external_id="tx1",
            posted_at=int(time.time()), amount=-100, description="Test",
        ))
        await db.commit()

        response = await client.get("/transactions/")
        tx = response.json()["transactions"][0]
        assert tx["category"] == "Uncategorized"

    @pytest.mark.asyncio
    async def test_transaction_response_includes_transacted_at_and_raw_data(self, client, db):
        """API response includes transacted_at and raw_data fields."""
        db.add(Account(id="act_1", provider="simplefin", name="Test"))
        db.add(Transaction(
            account_id="act_1", external_id="tx1",
            posted_at=int(time.time()), amount=-100, description="Test",
            transacted_at=1705190400,
            raw_data='{"simplefin_id":"tx1","pending":false,"extra":{"foo":"bar"}}',
        ))
        await db.commit()

        response = await client.get("/transactions/")
        tx = response.json()["transactions"][0]
        assert tx["transacted_at"] == 1705190400
        assert tx["raw_data"] is not None
        assert "foo" in tx["raw_data"]

    @pytest.mark.asyncio
    async def test_transaction_response_null_transacted_at(self, client, db):
        """API response returns null transacted_at when not set."""
        db.add(Account(id="act_1", provider="simplefin", name="Test"))
        db.add(Transaction(
            account_id="act_1", external_id="tx1",
            posted_at=int(time.time()), amount=-100, description="Test",
        ))
        await db.commit()

        response = await client.get("/transactions/")
        tx = response.json()["transactions"][0]
        assert tx["transacted_at"] is None

    @pytest.mark.asyncio
    async def test_filter_uncategorized(self, client, db):
        """Filter by category=Uncategorized returns only uncategorized transactions."""
        db.add(Account(id="act_1", provider="simplefin", name="Test"))
        db.add(Transaction(
            account_id="act_1", external_id="tx1",
            posted_at=int(time.time()), amount=-100, description="No Cat",
        ))
        db.add(Transaction(
            account_id="act_1", external_id="tx2",
            posted_at=int(time.time()), amount=-200, description="Has Cat",
            category="Food",
        ))
        await db.commit()

        response = await client.get("/transactions/", params={"category": "Uncategorized"})
        data = response.json()
        assert len(data["transactions"]) == 1
        assert data["transactions"][0]["description"] == "No Cat"

    @pytest.mark.asyncio
    async def test_list_transactions_returns_aggregates(self, client, db):
        """List transactions returns total_count, total_income, total_expenses."""
        db.add(Account(id="act_1", provider="simplefin", name="Test"))
        now = int(time.time())
        db.add_all([
            Transaction(account_id="act_1", external_id="tx1", posted_at=now, amount=-5000, description="Expense 1"),
            Transaction(account_id="act_1", external_id="tx2", posted_at=now, amount=-3000, description="Expense 2"),
            Transaction(account_id="act_1", external_id="tx3", posted_at=now, amount=10000, description="Income 1"),
        ])
        await db.commit()

        response = await client.get("/transactions/")
        data = response.json()
        assert data["total_count"] == 3
        assert data["total_income"] == 10000
        assert data["total_expenses"] == 8000

    @pytest.mark.asyncio
    async def test_list_transactions_sorting(self, client, db):
        """List transactions supports sorting by different columns."""
        db.add(Account(id="act_1", provider="simplefin", name="Test"))
        now = int(time.time())
        db.add_all([
            Transaction(account_id="act_1", external_id="tx1", posted_at=now, amount=-5000, description="Banana"),
            Transaction(account_id="act_1", external_id="tx2", posted_at=now, amount=-3000, description="Apple"),
            Transaction(account_id="act_1", external_id="tx3", posted_at=now, amount=-8000, description="Cherry"),
        ])
        await db.commit()

        # Sort by description asc
        response = await client.get("/transactions/", params={"sort_by": "description", "sort_order": "asc"})
        txns = response.json()["transactions"]
        assert txns[0]["description"] == "Apple"
        assert txns[1]["description"] == "Banana"
        assert txns[2]["description"] == "Cherry"

        # Sort by amount desc (least negative first = largest amount)
        response = await client.get("/transactions/", params={"sort_by": "amount", "sort_order": "desc"})
        txns = response.json()["transactions"]
        assert txns[0]["amount"] == -3000
        assert txns[2]["amount"] == -8000

    @pytest.mark.asyncio
    async def test_sort_by_account_name(self, client, db):
        """Sort by account name uses JOIN to Account table."""
        db.add(Account(id="act_a", provider="simplefin", name="Alpha Bank"))
        db.add(Account(id="act_z", provider="simplefin", name="Zeta Bank"))
        now = int(time.time())
        db.add(Transaction(account_id="act_z", external_id="tx1", posted_at=now, amount=-100, description="From Z"))
        db.add(Transaction(account_id="act_a", external_id="tx2", posted_at=now, amount=-200, description="From A"))
        await db.commit()

        response = await client.get("/transactions/", params={"sort_by": "account", "sort_order": "asc"})
        txns = response.json()["transactions"]
        assert txns[0]["description"] == "From A"
        assert txns[1]["description"] == "From Z"

    @pytest.mark.asyncio
    async def test_transaction_ids_endpoint(self, client, db):
        """GET /transactions/ids returns all matching IDs."""
        db.add(Account(id="act_1", provider="simplefin", name="Test"))
        now = int(time.time())
        db.add_all([
            Transaction(account_id="act_1", external_id="tx1", posted_at=now, amount=-100, description="A"),
            Transaction(account_id="act_1", external_id="tx2", posted_at=now, amount=-200, description="B"),
            Transaction(account_id="act_1", external_id="tx3", posted_at=now, amount=-300, description="C"),
        ])
        await db.commit()

        response = await client.get("/transactions/ids")
        assert response.status_code == 200
        data = response.json()
        assert len(data["ids"]) == 3

    @pytest.mark.asyncio
    async def test_transaction_ids_filtered(self, client, db):
        """GET /transactions/ids respects category filter."""
        db.add(Account(id="act_1", provider="simplefin", name="Test"))
        now = int(time.time())
        db.add_all([
            Transaction(account_id="act_1", external_id="tx1", posted_at=now, amount=-100, description="A", category="Food"),
            Transaction(account_id="act_1", external_id="tx2", posted_at=now, amount=-200, description="B"),
        ])
        await db.commit()

        response = await client.get("/transactions/ids", params={"category": "Uncategorized"})
        data = response.json()
        assert len(data["ids"]) == 1

        response = await client.get("/transactions/ids", params={"category": "Food"})
        data = response.json()
        assert len(data["ids"]) == 1


class TestProviderEndpoints:
    @pytest.mark.asyncio
    async def test_list_providers(self, client):
        """GET /providers/ returns all providers with status."""
        response = await client.get("/providers/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        simplefin = next(p for p in data if p["provider"] == "simplefin")
        assert simplefin["connected"] is False
        assert simplefin["display_name"] == "SimpleFIN Bridge"

    @pytest.mark.asyncio
    async def test_store_simplefin_credentials(self, client, db):
        """POST /providers/simplefin/credentials claims token and stores creds."""
        with patch("app.providers.simplefin.SimpleFINClient") as MockClient:
            MockClient.claim_setup_token = AsyncMock(
                return_value="https://user:pass@bridge.simplefin.org/simplefin"
            )

            response = await client.post(
                "/providers/simplefin/credentials",
                json={"setup_token": "dGVzdC1jbGFpbS11cmw="},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "simplefin"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_store_credentials_rejects_duplicate(self, client, db):
        """POST /providers/{name}/credentials rejects when creds already exist."""
        cred = Credential(
            id="cred_1",
            provider="simplefin",
            encrypted_data=encrypt(json.dumps({"access_url": "https://test@bridge.simplefin.org/simplefin"})),
        )
        db.add(cred)
        await db.commit()

        response = await client.post(
            "/providers/simplefin/credentials",
            json={"setup_token": "dGVzdC1jbGFpbS11cmw="},
        )
        assert response.status_code == 400
        assert "already configured" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_store_credentials_unknown_provider(self, client):
        """POST /providers/{name}/credentials returns 404 for unknown provider."""
        response = await client.post(
            "/providers/unknown/credentials",
            json={"foo": "bar"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_provider_credentials(self, client, db):
        """DELETE /providers/{name}/credentials deletes stored credentials."""
        cred = Credential(
            id="cred_1",
            provider="simplefin",
            encrypted_data=encrypt(json.dumps({"access_url": "https://test@bridge.simplefin.org/simplefin"})),
        )
        db.add(cred)
        await db.commit()

        response = await client.delete("/providers/simplefin/credentials")
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_credentials_404_when_none(self, client):
        """DELETE /providers/{name}/credentials returns 404 when no credentials exist."""
        response = await client.delete("/providers/simplefin/credentials")
        assert response.status_code == 404


class TestSyncEndpoints:
    @pytest.mark.asyncio
    async def test_trigger_sync_all(self, client, db):
        """POST /sync/ syncs all connected providers and returns 202."""
        from app.providers.models import SyncResult

        cred = Credential(
            id="cred_1",
            provider="simplefin",
            encrypted_data=encrypt(json.dumps({
                "access_url": "https://user:pass@bridge.simplefin.org/simplefin",
            })),
        )
        db.add(cred)
        await db.commit()

        mock_result = SyncResult(
            accounts=[], transactions=[], errors=[], raw_json="{}",
        )
        mock_provider = AsyncMock()
        mock_provider.provider_name = "simplefin"
        mock_provider.display_name = "SimpleFIN Bridge"
        mock_provider.max_syncs_per_day = 24
        mock_provider.sync = AsyncMock(return_value=mock_result)

        with patch("app.services.sync.get_provider", return_value=mock_provider):
            response = await client.post("/sync/")

        assert response.status_code == 202
        data = response.json()
        assert "sync_ids" in data
        assert len(data["sync_ids"]) == 1

    @pytest.mark.asyncio
    async def test_trigger_sync_no_providers(self, client):
        """POST /sync/ returns 400 when no providers connected."""
        response = await client.post("/sync/")
        assert response.status_code == 400
        assert "No providers connected" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_trigger_sync_one_provider(self, client, db):
        """POST /sync/{provider} syncs one provider."""
        from app.providers.models import SyncResult

        cred = Credential(
            id="cred_1",
            provider="simplefin",
            encrypted_data=encrypt(json.dumps({
                "access_url": "https://user:pass@bridge.simplefin.org/simplefin",
            })),
        )
        db.add(cred)
        await db.commit()

        mock_result = SyncResult(
            accounts=[], transactions=[], errors=[], raw_json="{}",
        )
        mock_provider = AsyncMock()
        mock_provider.provider_name = "simplefin"
        mock_provider.display_name = "SimpleFIN Bridge"
        mock_provider.max_syncs_per_day = 24
        mock_provider.sync = AsyncMock(return_value=mock_result)

        with patch("app.services.sync.get_provider", return_value=mock_provider):
            response = await client.post("/sync/simplefin")

        assert response.status_code == 202
        data = response.json()
        assert len(data["sync_ids"]) == 1

    @pytest.mark.asyncio
    async def test_trigger_sync_unknown_provider(self, client):
        """POST /sync/{provider} returns 404 for unknown provider."""
        response = await client.post("/sync/unknown")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_sync_status(self, client, db):
        """GET /sync/status returns per-provider sync status."""
        response = await client.get("/sync/status")
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert "any_running" in data
        assert data["any_running"] is False

    @pytest.mark.asyncio
    async def test_sync_logs(self, client, db):
        """GET /sync/logs returns recent sync history."""
        now = int(time.time())
        db.add(SyncLog(
            provider="simplefin",
            started_at=now,
            completed_at=now,
            status="success",
            accounts_synced=2,
            transactions_added=10,
        ))
        await db.commit()

        response = await client.get("/sync/logs")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["provider"] == "simplefin"
        assert data[0]["status"] == "success"


class TestAnalyticsEndpoint:
    @pytest.mark.asyncio
    async def test_spending_by_category(self, client, db):
        """Get spending grouped by category."""
        account = Account(
            id="act_1",
            provider="simplefin",
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

    @pytest.mark.asyncio
    async def test_analytics_excludes_disabled_accounts(self, client, db):
        """Analytics spending excludes disabled account transactions."""
        db.add(Account(id="act_1", provider="simplefin", name="Visible"))
        db.add(Account(id="act_2", provider="simplefin", name="Hidden", is_disabled=True))
        now = int(time.time())
        db.add(Transaction(
            account_id="act_1", external_id="tx1",
            posted_at=now, amount=-5000, description="A", category="Food",
        ))
        db.add(Transaction(
            account_id="act_2", external_id="tx2",
            posted_at=now, amount=-3000, description="B", category="Food",
        ))
        await db.commit()

        response = await client.get("/analytics/spending-by-category")
        data = response.json()
        categories = {c["category"]: c for c in data["categories"]}
        assert categories["Food"]["total"] == 5000  # Only from enabled account


class TestCategorizeEndpoint:
    @pytest.mark.asyncio
    async def test_categorize_no_categories_guard(self, client, db):
        """POST /llm/categorize returns error when no categories exist."""
        from app.clients.gemini import GeminiClient
        from app.routes.llm import _get_client

        mock_client = AsyncMock(spec=GeminiClient)
        app = client._transport.app
        app.dependency_overrides[_get_client] = lambda: mock_client

        # Create uncategorized transaction (no categories in DB)
        db.add(Account(id="act_1", provider="simplefin", name="Test"))
        db.add(Transaction(
            account_id="act_1", external_id="tx1",
            posted_at=int(time.time()), amount=-100, description="Test",
        ))
        await db.commit()

        response = await client.post("/llm/categorize")
        assert response.status_code == 200
        data = response.json()
        assert data["total_processed"] == 0
        assert data["error"] == "No categories configured. Add categories before running categorization."

        del app.dependency_overrides[_get_client]
