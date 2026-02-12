"""Tests for category CRUD endpoints."""

import time

import pytest

from app.models import Account, Category, Transaction


class TestCategoryEndpoints:
    @pytest.mark.asyncio
    async def test_list_categories_empty(self, client):
        resp = await client.get("/categories/")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_create_category(self, client):
        resp = await client.post(
            "/categories/",
            json={"name": "Test Category", "description": "A test"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Category"
        assert data["description"] == "A test"
        assert data["is_default"] is False

    @pytest.mark.asyncio
    async def test_create_category_duplicate(self, client):
        await client.post("/categories/", json={"name": "Dup"})
        resp = await client.post("/categories/", json={"name": "Dup"})
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_categories(self, client):
        await client.post("/categories/", json={"name": "B Category"})
        await client.post("/categories/", json={"name": "A Category"})
        resp = await client.get("/categories/")
        assert resp.status_code == 200
        names = [c["name"] for c in resp.json()]
        assert names == ["A Category", "B Category"]  # sorted

    @pytest.mark.asyncio
    async def test_delete_category(self, client):
        create_resp = await client.post("/categories/", json={"name": "ToDelete"})
        cat_id = create_resp.json()["id"]

        resp = await client.delete(f"/categories/{cat_id}")
        assert resp.status_code == 200

        # Verify it's gone
        list_resp = await client.get("/categories/")
        assert all(c["name"] != "ToDelete" for c in list_resp.json())

    @pytest.mark.asyncio
    async def test_delete_category_not_found(self, client):
        resp = await client.delete("/categories/999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_default_category_forbidden(self, client, db):
        cat = Category(name="Default Cat", is_default=True, created_at=int(time.time()))
        db.add(cat)
        await db.flush()

        resp = await client.delete(f"/categories/{cat.id}")
        assert resp.status_code == 400
        assert "default" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_delete_category_nullifies_transactions(self, client, db):
        from app.models import Account

        # Create account, transaction, and category
        now = int(time.time())
        account = Account(id="acc-1", name="Test", created_at=now)
        db.add(account)
        await db.flush()

        tx = Transaction(
            account_id="acc-1",
            external_id="tx-1",
            posted_at=now,
            amount=-1000,
            description="Test tx",
            category="ToDelete",
            created_at=now,
        )
        db.add(tx)
        await db.flush()

        create_resp = await client.post("/categories/", json={"name": "ToDelete"})
        cat_id = create_resp.json()["id"]

        # Delete category
        await client.delete(f"/categories/{cat_id}")

        # Verify transaction category is reset to Uncategorized
        resp = await client.get("/transactions/", params={"search": "Test tx"})
        txns = resp.json()["transactions"]
        assert len(txns) == 1
        assert txns[0]["category"] == "Uncategorized"

    @pytest.mark.asyncio
    async def test_patch_category_exclude_from_totals(self, client, db):
        """PATCH /categories/{id} toggles exclude_from_totals."""
        cat = Category(name="Transfers", is_default=True, created_at=int(time.time()))
        db.add(cat)
        await db.flush()

        # Toggle on
        resp = await client.patch(
            f"/categories/{cat.id}",
            json={"exclude_from_totals": True},
        )
        assert resp.status_code == 200
        assert resp.json()["exclude_from_totals"] is True

        # Toggle off
        resp = await client.patch(
            f"/categories/{cat.id}",
            json={"exclude_from_totals": False},
        )
        assert resp.status_code == 200
        assert resp.json()["exclude_from_totals"] is False

    @pytest.mark.asyncio
    async def test_patch_category_not_found(self, client):
        """PATCH /categories/999 returns 404."""
        resp = await client.patch(
            "/categories/999",
            json={"exclude_from_totals": True},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_category_description(self, client):
        """PATCH can update description."""
        create_resp = await client.post(
            "/categories/", json={"name": "Custom"},
        )
        cat_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/categories/{cat_id}",
            json={"description": "Updated description"},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated description"


class TestAccountOrdering:
    @pytest.mark.asyncio
    async def test_accounts_sorted_by_absolute_balance(self, client, db):
        """Accounts are returned sorted by absolute balance descending."""
        now = int(time.time())
        db.add(Account(id="small", provider="simplefin", name="Small", balance_current=1000, created_at=now))
        db.add(Account(id="big_neg", provider="simplefin", name="Big Loan", balance_current=-50000, created_at=now))
        db.add(Account(id="big_pos", provider="simplefin", name="Savings", balance_current=40000, created_at=now))
        db.add(Account(id="zero", provider="simplefin", name="Empty", balance_current=0, created_at=now))
        await db.commit()

        resp = await client.get("/accounts/")
        assert resp.status_code == 200
        ids = [a["id"] for a in resp.json()]
        # Big loan (-50000), Savings (40000), Small (1000), Empty (0)
        assert ids == ["big_neg", "big_pos", "small", "zero"]

    @pytest.mark.asyncio
    async def test_accounts_null_balance_sorted_last(self, client, db):
        """Accounts with null balance sort after accounts with balance."""
        now = int(time.time())
        db.add(Account(id="has_balance", provider="simplefin", name="Has", balance_current=5000, created_at=now))
        db.add(Account(id="no_balance", provider="simplefin", name="None", balance_current=None, created_at=now))
        await db.commit()

        resp = await client.get("/accounts/")
        ids = [a["id"] for a in resp.json()]
        assert ids == ["has_balance", "no_balance"]
