"""Tests for API endpoints."""

import json
import os
import time

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set test encryption key before importing app modules
os.environ["ENCRYPTION_KEY"] = "eBKqFlbjULz6MZKcre8TswaoEFBrG8pGBmFXlOT6MOs="

from app.main import app
from app.models import Account, Base, Credential, SyncLog, Transaction
from app.database import get_db
from app.encryption import encrypt


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def test_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def client(test_db):
    """Create test client with overridden database dependency."""

    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


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
    async def test_health_shows_last_sync(self, client, test_db):
        """Health endpoint shows last sync info."""
        # Create a sync log
        sync_log = SyncLog(
            started_at=int(time.time()),
            completed_at=int(time.time()),
            status="success",
            accounts_synced=2,
            transactions_added=10,
        )
        test_db.add(sync_log)
        await test_db.commit()

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
    async def test_list_accounts(self, client, test_db):
        """List accounts returns all accounts."""
        account = Account(
            id="act_1",
            provider="simplefin",
            org_domain="chase.com",
            org_name="Chase",
            name="Chase Checking",
            balance_current=123456,
        )
        test_db.add(account)
        await test_db.commit()

        response = await client.get("/accounts/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "act_1"
        assert data[0]["name"] == "Chase Checking"

    @pytest.mark.asyncio
    async def test_get_account(self, client, test_db):
        """Get specific account by ID."""
        account = Account(
            id="act_1",
            provider="simplefin",
            org_domain="chase.com",
            name="Chase Checking",
        )
        test_db.add(account)
        await test_db.commit()

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
    async def test_list_transactions(self, client, test_db):
        """List transactions with filters."""
        account = Account(
            id="act_1",
            provider="simplefin",
            org_domain="chase.com",
            name="Test Account",
        )
        test_db.add(account)

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
        test_db.add_all([tx1, tx2])
        await test_db.commit()

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
    async def test_update_transaction(self, client, test_db):
        """Update transaction category and notes."""
        account = Account(
            id="act_1",
            provider="simplefin",
            org_domain="chase.com",
            name="Test Account",
        )
        test_db.add(account)

        tx = Transaction(
            account_id="act_1",
            external_id="tx_1",
            posted_at=int(time.time()),
            amount=-5000,
            description="Coffee",
        )
        test_db.add(tx)
        await test_db.commit()

        response = await client.patch(
            f"/transactions/{tx.id}",
            json={"category": "Food & Dining", "notes": "Morning coffee"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "Food & Dining"
        assert data["notes"] == "Morning coffee"


class TestAnalyticsEndpoint:
    @pytest.mark.asyncio
    async def test_spending_by_category(self, client, test_db):
        """Get spending grouped by category."""
        account = Account(
            id="act_1",
            provider="simplefin",
            org_domain="chase.com",
            name="Test Account",
        )
        test_db.add(account)

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
        test_db.add_all(transactions)
        await test_db.commit()

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
