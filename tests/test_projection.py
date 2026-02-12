"""Tests for income projection and user settings."""

import json
import time

import pytest

from app.models import Account, Transaction, UserSetting


class TestSettingsEndpoints:
    @pytest.mark.asyncio
    async def test_put_and_get_setting(self, client, db):
        """PUT creates a setting, GET retrieves it."""
        resp = await client.put(
            "/settings/projection_return_rates",
            json={"value": {"low": 0.03}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "projection_return_rates"
        assert data["value"] == {"low": 0.03}

        resp = await client.get("/settings/projection_return_rates")
        assert resp.status_code == 200
        assert resp.json()["value"] == {"low": 0.03}

    @pytest.mark.asyncio
    async def test_put_updates_existing(self, client, db):
        """PUT overwrites an existing setting."""
        await client.put("/settings/projection_monthly_contribution", json={"value": 100})
        await client.put("/settings/projection_monthly_contribution", json={"value": 200})
        resp = await client.get("/settings/projection_monthly_contribution")
        assert resp.json()["value"] == 200

    @pytest.mark.asyncio
    async def test_get_not_found(self, client):
        """GET /settings/nonexistent returns 404."""
        resp = await client.get("/settings/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_put_invalid_key(self, client):
        """PUT /settings/unknown_key returns 400."""
        resp = await client.put("/settings/unknown_key", json={"value": 42})
        assert resp.status_code == 400
        assert "Unknown setting key" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_setting(self, client, db):
        """DELETE removes a setting."""
        await client.put("/settings/projection_monthly_contribution", json={"value": 42})
        resp = await client.delete("/settings/projection_monthly_contribution")
        assert resp.status_code == 200

        resp = await client.get("/settings/projection_monthly_contribution")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client):
        """DELETE /settings/nonexistent returns 404."""
        resp = await client.delete("/settings/nonexistent")
        assert resp.status_code == 404


class TestIncomeProjection:
    @pytest.mark.asyncio
    async def test_projection_empty_data(self, client):
        """Projection with no data returns zeroed values."""
        resp = await client.get("/analytics/income-projection")
        assert resp.status_code == 200
        data = resp.json()
        assert data["monthly_income"] == 0
        assert data["monthly_expenses"] == 0
        assert data["monthly_contribution"] == 0
        assert data["is_configured"] is False
        assert len(data["bands"]) == 3
        # All bands should have 0 balance since contribution is 0
        for band in data["bands"]:
            assert band["points"][-1]["balance"] == 0

    @pytest.mark.asyncio
    async def test_projection_auto_calculated(self, client, db):
        """Projection auto-calculates from transaction history."""
        db.add(Account(id="act_1", provider="simplefin", name="Chase"))
        now = int(time.time())
        # Add 3 months of income and expenses
        for i in range(3):
            month_ts = now - ((2 - i) * 30 * 86400)
            db.add(Transaction(
                account_id="act_1", external_id=f"pay_{i}",
                posted_at=month_ts, amount=500000,
                description="PAYCHECK",
            ))
            db.add(Transaction(
                account_id="act_1", external_id=f"exp_{i}",
                posted_at=month_ts, amount=-300000,
                description="RENT",
            ))
        await db.commit()

        resp = await client.get("/analytics/income-projection")
        data = resp.json()
        assert data["monthly_income"] > 0
        assert data["monthly_expenses"] > 0
        assert data["monthly_contribution"] > 0
        assert data["is_configured"] is False

    @pytest.mark.asyncio
    async def test_projection_with_configured_sources(self, client, db):
        """Projection uses configured income sources."""
        db.add(UserSetting(
            key="projection_income_sources",
            value=json.dumps([
                {"name": "My Salary", "monthly_amount": 600000},
                {"name": "Wife Salary", "monthly_amount": 400000},
            ]),
            updated_at=int(time.time()),
        ))
        await db.commit()

        resp = await client.get("/analytics/income-projection")
        data = resp.json()
        assert data["monthly_income"] == 1000000  # 600000 + 400000
        assert data["is_configured"] is True
        assert len(data["income_sources"]) == 2

    @pytest.mark.asyncio
    async def test_projection_compound_growth(self, client):
        """Verify compound growth math — 10% annual for 1 year with $1000/mo contribution."""
        resp = await client.get("/analytics/income-projection", params={
            "time_horizon_years": 1,
        })
        data = resp.json()
        # Find the average (10%) band
        avg_band = next(b for b in data["bands"] if abs(b["annual_return"] - 0.10) < 0.01)
        # Year 0 should be 0
        assert avg_band["points"][0]["balance"] == 0
        # Year 1 contributions should be 0 (no contribution since no data)

    @pytest.mark.asyncio
    async def test_projection_with_contribution_override(self, client, db):
        """Configured monthly contribution overrides auto-calculation."""
        db.add(UserSetting(
            key="projection_monthly_contribution",
            value=json.dumps(200000),  # $2000/mo
            updated_at=int(time.time()),
        ))
        await db.commit()

        resp = await client.get("/analytics/income-projection", params={
            "time_horizon_years": 1,
        })
        data = resp.json()
        assert data["monthly_contribution"] == 200000
        assert data["is_configured"] is True
        # After 1 year of $2000/mo at 10%, should be > $24000 (contributions only)
        avg_band = next(b for b in data["bands"] if abs(b["annual_return"] - 0.10) < 0.01)
        assert avg_band["points"][-1]["balance"] > 2400000  # More than contributions due to growth
        assert avg_band["points"][-1]["contributions"] == 2400000  # 200000 * 12

    @pytest.mark.asyncio
    async def test_projection_bands_ordered(self, client):
        """Projection returns 3 bands (low, average, high)."""
        resp = await client.get("/analytics/income-projection")
        data = resp.json()
        assert len(data["bands"]) == 3
        rates = [b["annual_return"] for b in data["bands"]]
        assert 0.04 in rates
        assert 0.10 in rates
        assert 0.14 in rates
