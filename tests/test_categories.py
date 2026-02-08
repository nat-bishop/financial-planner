"""Tests for category CRUD endpoints."""

import time

import pytest

from app.models import Category, Transaction


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
    async def test_update_category(self, client):
        create_resp = await client.post("/categories/", json={"name": "Old"})
        cat_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/categories/{cat_id}",
            json={"name": "New", "description": "Updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"
        assert resp.json()["description"] == "Updated"

    @pytest.mark.asyncio
    async def test_update_category_not_found(self, client):
        resp = await client.patch("/categories/999", json={"name": "X"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_category_duplicate_name(self, client):
        await client.post("/categories/", json={"name": "Cat1"})
        create2 = await client.post("/categories/", json={"name": "Cat2"})
        cat2_id = create2.json()["id"]

        resp = await client.patch(f"/categories/{cat2_id}", json={"name": "Cat1"})
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

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
        resp = await client.get(f"/transactions/{tx.id}")
        assert resp.json()["category"] == "Uncategorized"
