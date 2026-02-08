"""Tests for LLM endpoints (categorization + chat)."""

import time
from unittest.mock import AsyncMock, patch

import pytest

from app.clients.gemini import GeminiClient
from app.main import app
from app.models import Account, Category, Transaction
from app.routes.llm import _get_client
from app.schemas import BatchCategorizationResponse, TransactionCategorization


def _seed_categories(db):
    """Add a few default categories to the DB."""
    now = int(time.time())
    cats = [
        Category(name="Food & Dining", description="Groceries, restaurants", is_default=True, created_at=now),
        Category(name="Transportation", description="Gas, parking, tolls", is_default=True, created_at=now),
        Category(name="Shopping", description="Clothing, electronics", is_default=True, created_at=now),
    ]
    for c in cats:
        db.add(c)


def _seed_transactions(db, count=3):
    """Add test transactions."""
    now = int(time.time())
    account = Account(id="test-acc", name="Test Checking", org_name="Test Bank", created_at=now)
    db.add(account)

    txs = []
    for i in range(count):
        tx = Transaction(
            account_id="test-acc",
            external_id=f"tx-{i}",
            posted_at=now - i * 86400,
            amount=-1500 - i * 100,
            description=["WHOLE FOODS MKT", "SHELL GAS", "AMAZON.COM"][i % 3],
            created_at=now,
        )
        db.add(tx)
        txs.append(tx)
    return txs


class TestLLMStatus:
    @pytest.mark.asyncio
    async def test_status_unconfigured(self, client):
        with patch("app.core.config.settings.gemini_api_key", ""):
            resp = await client.get("/llm/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False
        assert "model" in data

    @pytest.mark.asyncio
    async def test_status_configured(self, client):
        with patch("app.core.config.settings.gemini_api_key", "test-key"):
            resp = await client.get("/llm/status")
            assert resp.status_code == 200
            assert resp.json()["configured"] is True


class TestCategorize:
    @pytest.mark.asyncio
    async def test_categorize_no_api_key(self, client):
        with (
            patch("app.core.config.settings.gemini_api_key", ""),
            patch("app.clients.gemini._client", None),
        ):
            resp = await client.post("/llm/categorize")
        assert resp.status_code == 400
        assert "GEMINI_API_KEY" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_categorize_uncategorized(self, client, db):
        _seed_categories(db)
        txs = _seed_transactions(db)
        await db.flush()

        # Mock the Gemini client
        mock_client = AsyncMock(spec=GeminiClient)
        mock_client.generate_structured = AsyncMock(
            return_value=BatchCategorizationResponse(
                transactions=[
                    TransactionCategorization(
                        id=txs[0].id,
                        category="Food & Dining",
                        subcategory="Groceries",
                        confidence=0.95,
                        reasoning="Whole Foods is a grocery store",
                    ),
                    TransactionCategorization(
                        id=txs[1].id,
                        category="Transportation",
                        subcategory="Gas",
                        confidence=0.90,
                        reasoning="Shell is a gas station",
                    ),
                    TransactionCategorization(
                        id=txs[2].id,
                        category="Shopping",
                        subcategory="Online Shopping",
                        confidence=0.45,  # Below default 0.7 threshold
                        reasoning="Amazon sells many categories",
                    ),
                ]
            )
        )

        app.dependency_overrides[_get_client] = lambda: mock_client

        try:
            resp = await client.post("/llm/categorize")
            assert resp.status_code == 200
            data = resp.json()

            assert data["total_processed"] == 3
            assert data["categorized"] == 2
            assert data["unable_to_categorize"] == 1

            # Check results
            results = {r["transaction_id"]: r for r in data["results"]}

            # High confidence - applied
            assert results[txs[0].id]["category"] == "Food & Dining"
            assert results[txs[0].id]["applied"] is True
            assert results[txs[0].id]["subcategory"] == "Groceries"

            # Low confidence - unable to categorize
            assert results[txs[2].id]["category"] == "Unable to Categorize"
            assert results[txs[2].id]["suggested_category"] == "Shopping"
            assert results[txs[2].id]["applied"] is False
        finally:
            app.dependency_overrides.pop(_get_client, None)

    @pytest.mark.asyncio
    async def test_categorize_specific_ids(self, client, db):
        _seed_categories(db)
        txs = _seed_transactions(db)
        # Pre-categorize one
        txs[0].category = "Old Category"
        await db.flush()

        mock_client = AsyncMock(spec=GeminiClient)
        mock_client.generate_structured = AsyncMock(
            return_value=BatchCategorizationResponse(
                transactions=[
                    TransactionCategorization(
                        id=txs[0].id,
                        category="Food & Dining",
                        subcategory="Groceries",
                        confidence=0.95,
                        reasoning="Re-categorized",
                    ),
                ]
            )
        )

        app.dependency_overrides[_get_client] = lambda: mock_client

        try:
            resp = await client.post(
                "/llm/categorize",
                json={"transaction_ids": [txs[0].id]},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_processed"] == 1
            assert data["results"][0]["category"] == "Food & Dining"
        finally:
            app.dependency_overrides.pop(_get_client, None)

    @pytest.mark.asyncio
    async def test_categorize_empty(self, client, db):
        """No uncategorized transactions returns empty result."""
        _seed_categories(db)
        txs = _seed_transactions(db, count=1)
        txs[0].category = "Already Set"
        await db.flush()

        mock_client = AsyncMock(spec=GeminiClient)
        app.dependency_overrides[_get_client] = lambda: mock_client

        try:
            resp = await client.post("/llm/categorize")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_processed"] == 0
            mock_client.generate_structured.assert_not_called()
        finally:
            app.dependency_overrides.pop(_get_client, None)


class TestChat:
    @pytest.mark.asyncio
    async def test_chat_no_api_key(self, client):
        with (
            patch("app.core.config.settings.gemini_api_key", ""),
            patch("app.clients.gemini._client", None),
        ):
            resp = await client.post("/llm/chat", json={"message": "hello"})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_chat_streams(self, client, db):
        mock_client = AsyncMock(spec=GeminiClient)

        async def mock_stream(*args, **kwargs):
            yield "Hello "
            yield "World"

        mock_client.stream = mock_stream

        app.dependency_overrides[_get_client] = lambda: mock_client

        try:
            resp = await client.post("/llm/chat", json={"message": "hello"})
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            body = resp.text
            assert "Hello " in body
            assert "World" in body
            assert "[DONE]" in body
        finally:
            app.dependency_overrides.pop(_get_client, None)


class TestTransactionFilters:
    @pytest.mark.asyncio
    async def test_filter_uncategorized(self, client, db):
        now = int(time.time())
        account = Account(id="acc-f", name="Filter Test", created_at=now)
        db.add(account)

        tx1 = Transaction(
            account_id="acc-f", external_id="f-1", posted_at=now,
            amount=-100, description="Categorized", category="Food & Dining", created_at=now,
        )
        tx2 = Transaction(
            account_id="acc-f", external_id="f-2", posted_at=now,
            amount=-200, description="Uncategorized", category="Uncategorized", created_at=now,
        )
        db.add_all([tx1, tx2])
        await db.flush()

        resp = await client.get("/transactions/", params={"category": "Uncategorized"})
        assert resp.status_code == 200
        data = resp.json()["transactions"]
        assert len(data) == 1
        assert data[0]["description"] == "Uncategorized"

    @pytest.mark.asyncio
    async def test_filter_by_category_exact(self, client, db):
        now = int(time.time())
        account = Account(id="acc-g", name="Cat Filter", created_at=now)
        db.add(account)

        tx1 = Transaction(
            account_id="acc-g", external_id="g-1", posted_at=now,
            amount=-100, description="T1", category="Unable to Categorize", created_at=now,
        )
        tx2 = Transaction(
            account_id="acc-g", external_id="g-2", posted_at=now,
            amount=-200, description="T2", category="Food & Dining", created_at=now,
        )
        db.add_all([tx1, tx2])
        await db.flush()

        resp = await client.get("/transactions/", params={"category": "Unable to Categorize"})
        assert resp.status_code == 200
        data = resp.json()["transactions"]
        assert len(data) == 1
        assert data[0]["category"] == "Unable to Categorize"
