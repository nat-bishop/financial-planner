"""Tests for recurring transaction detection."""

import time

import pytest

from app.models import Account, Transaction
from app.services.recurring import detect_recurring


class TestRecurringDetection:
    @pytest.mark.asyncio
    async def test_detect_monthly_pattern(self, db):
        """Detects monthly recurring transactions."""
        db.add(Account(id="act_1", provider="simplefin", name="Chase"))
        base = int(time.time()) - (150 * 86400)  # 150 days ago
        for i in range(5):
            db.add(Transaction(
                account_id="act_1",
                external_id=f"tx_{i}",
                posted_at=base + (i * 30 * 86400),
                amount=-5000,
                description="NETFLIX SUBSCRIPTION",
            ))
        await db.commit()

        patterns = await detect_recurring(db, lookback_months=12, direction="expense")
        assert len(patterns) == 1
        p = patterns[0]
        assert p.description == "netflix subscription"
        assert p.frequency == "monthly"
        assert p.median_amount == 5000
        assert p.occurrence_count == 5
        assert p.confidence > 0.9

    @pytest.mark.asyncio
    async def test_detect_biweekly_pattern(self, db):
        """Detects biweekly recurring transactions."""
        db.add(Account(id="act_1", provider="simplefin", name="Chase"))
        base = int(time.time()) - (90 * 86400)
        for i in range(6):
            db.add(Transaction(
                account_id="act_1",
                external_id=f"tx_{i}",
                posted_at=base + (i * 14 * 86400),
                amount=-10000,
                description="MORTGAGE PAYMENT",
            ))
        await db.commit()

        patterns = await detect_recurring(db, lookback_months=12, direction="expense")
        assert len(patterns) == 1
        assert patterns[0].frequency == "biweekly"

    @pytest.mark.asyncio
    async def test_reject_too_few_occurrences(self, db):
        """Does not detect patterns with fewer than 3 occurrences."""
        db.add(Account(id="act_1", provider="simplefin", name="Chase"))
        base = int(time.time()) - (60 * 86400)
        for i in range(2):
            db.add(Transaction(
                account_id="act_1",
                external_id=f"tx_{i}",
                posted_at=base + (i * 30 * 86400),
                amount=-5000,
                description="RARE PAYMENT",
            ))
        await db.commit()

        patterns = await detect_recurring(db, lookback_months=12, direction="expense")
        assert len(patterns) == 0

    @pytest.mark.asyncio
    async def test_reject_irregular_intervals(self, db):
        """Does not detect patterns with irregular intervals."""
        db.add(Account(id="act_1", provider="simplefin", name="Chase"))
        base = int(time.time()) - (200 * 86400)
        # Highly irregular intervals: 5, 50, 10, 40 days
        offsets = [0, 5, 55, 65, 105]
        for i, offset in enumerate(offsets):
            db.add(Transaction(
                account_id="act_1",
                external_id=f"tx_{i}",
                posted_at=base + (offset * 86400),
                amount=-3000,
                description="RANDOM STORE",
            ))
        await db.commit()

        patterns = await detect_recurring(db, lookback_months=12, direction="expense")
        assert len(patterns) == 0

    @pytest.mark.asyncio
    async def test_excludes_disabled_accounts(self, db):
        """Does not detect patterns from disabled accounts."""
        db.add(Account(id="act_1", provider="simplefin", name="Hidden", is_disabled=True))
        base = int(time.time()) - (120 * 86400)
        for i in range(4):
            db.add(Transaction(
                account_id="act_1",
                external_id=f"tx_{i}",
                posted_at=base + (i * 30 * 86400),
                amount=-5000,
                description="NETFLIX",
            ))
        await db.commit()

        patterns = await detect_recurring(db, lookback_months=12, direction="expense")
        assert len(patterns) == 0

    @pytest.mark.asyncio
    async def test_predicted_next_date(self, db):
        """Predicted next date is last occurrence + median interval."""
        db.add(Account(id="act_1", provider="simplefin", name="Chase"))
        base = int(time.time()) - (90 * 86400)
        for i in range(4):
            db.add(Transaction(
                account_id="act_1",
                external_id=f"tx_{i}",
                posted_at=base + (i * 30 * 86400),
                amount=-5000,
                description="MONTHLY BILL",
            ))
        await db.commit()

        patterns = await detect_recurring(db, lookback_months=12, direction="expense")
        assert len(patterns) == 1
        last_ts = base + (3 * 30 * 86400)
        # Predicted next should be ~30 days after last
        assert abs(patterns[0].predicted_next - (last_ts + 30 * 86400)) < 86400  # within 1 day

    @pytest.mark.asyncio
    async def test_direction_income(self, db):
        """Direction 'income' finds recurring income (paychecks)."""
        db.add(Account(id="act_1", provider="simplefin", name="Chase"))
        base = int(time.time()) - (120 * 86400)
        for i in range(4):
            # Paycheck
            db.add(Transaction(
                account_id="act_1",
                external_id=f"pay_{i}",
                posted_at=base + (i * 14 * 86400),
                amount=200000,
                description="EMPLOYER DIRECT DEPOSIT",
            ))
            # Bill (should be excluded when direction=income)
            db.add(Transaction(
                account_id="act_1",
                external_id=f"bill_{i}",
                posted_at=base + (i * 30 * 86400),
                amount=-5000,
                description="NETFLIX",
            ))
        await db.commit()

        income_patterns = await detect_recurring(db, lookback_months=12, direction="income")
        assert len(income_patterns) == 1
        assert income_patterns[0].description == "employer direct deposit"

        expense_patterns = await detect_recurring(db, lookback_months=12, direction="expense")
        assert len(expense_patterns) == 1
        assert expense_patterns[0].description == "netflix"

    @pytest.mark.asyncio
    async def test_normalizes_descriptions(self, db):
        """Groups transactions by normalized description (strips dates/refs)."""
        db.add(Account(id="act_1", provider="simplefin", name="Chase"))
        base = int(time.time()) - (120 * 86400)
        descs = [
            "BILT PAYMENT 01/15",
            "BILT PAYMENT 02/15",
            "BILT PAYMENT 03/15",
            "BILT PAYMENT 04/15",
        ]
        for i, desc in enumerate(descs):
            db.add(Transaction(
                account_id="act_1",
                external_id=f"tx_{i}",
                posted_at=base + (i * 30 * 86400),
                amount=-150000,
                description=desc,
            ))
        await db.commit()

        patterns = await detect_recurring(db, lookback_months=12, direction="expense")
        assert len(patterns) == 1
        assert patterns[0].description == "bilt payment"


class TestRecurringBillsEndpoint:
    @pytest.mark.asyncio
    async def test_recurring_bills_api(self, client, db):
        """GET /analytics/recurring-bills returns detected bills."""
        db.add(Account(id="act_1", provider="simplefin", name="Chase"))
        base = int(time.time()) - (120 * 86400)
        for i in range(4):
            db.add(Transaction(
                account_id="act_1",
                external_id=f"tx_{i}",
                posted_at=base + (i * 30 * 86400),
                amount=-1500,
                description="SPOTIFY",
            ))
        await db.commit()

        response = await client.get("/analytics/recurring-bills")
        assert response.status_code == 200
        data = response.json()
        assert data["lookback_months"] == 6
        assert len(data["bills"]) == 1
        assert data["bills"][0]["frequency"] == "monthly"
        assert data["bills"][0]["median_amount"] == 1500

    @pytest.mark.asyncio
    async def test_recurring_bills_empty(self, client):
        """GET /analytics/recurring-bills returns empty list with no transactions."""
        response = await client.get("/analytics/recurring-bills")
        assert response.status_code == 200
        assert response.json()["bills"] == []
