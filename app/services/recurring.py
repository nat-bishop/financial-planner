"""Recurring transaction detection service."""

import statistics
import time
from collections import defaultdict
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Account,
    Transaction,
    exclude_disabled_accounts,
    normalize_description,
)


def _classify_frequency(median_days: float) -> str | None:
    """Classify a median interval (in days) into a named frequency."""
    if 6 <= median_days <= 8:
        return "weekly"
    if 13 <= median_days <= 16:
        return "biweekly"
    if 27 <= median_days <= 33:
        return "monthly"
    if 55 <= median_days <= 65:
        return "bimonthly"
    if 85 <= median_days <= 95:
        return "quarterly"
    if 170 <= median_days <= 195:
        return "semiannual"
    if 350 <= median_days <= 380:
        return "annual"
    return None


def _max_std_dev(frequency: str) -> float:
    """Maximum allowed standard deviation (days) for a frequency to be considered regular."""
    return {
        "weekly": 2,
        "biweekly": 3,
        "monthly": 5,
        "bimonthly": 7,
        "quarterly": 10,
        "semiannual": 15,
        "annual": 20,
    }.get(frequency, 5)


class RecurringPattern:
    """Detected recurring transaction pattern."""

    def __init__(
        self,
        *,
        description: str,
        raw_description: str,
        account_id: str,
        account_name: str,
        frequency: str,
        median_amount: int,
        last_occurrence: int,
        predicted_next: int,
        occurrence_count: int,
        confidence: float,
    ):
        self.description = description
        self.raw_description = raw_description
        self.account_id = account_id
        self.account_name = account_name
        self.frequency = frequency
        self.median_amount = median_amount
        self.last_occurrence = last_occurrence
        self.predicted_next = predicted_next
        self.occurrence_count = occurrence_count
        self.confidence = confidence


async def detect_recurring(
    db: AsyncSession,
    lookback_months: int = 6,
    direction: Literal["expense", "income", "all"] = "expense",
) -> list[RecurringPattern]:
    """Detect recurring transactions by analyzing patterns in transaction history.

    Args:
        db: Database session
        lookback_months: How far back to look for patterns
        direction: "expense" for bills, "income" for paychecks, "all" for both
    """
    now = int(time.time())
    start_ts = now - (lookback_months * 30 * 24 * 60 * 60)

    # Build query
    query = (
        select(Transaction, Account.name.label("account_name"))
        .join(Account, Transaction.account_id == Account.id)
        .where(Transaction.posted_at >= start_ts)
    )
    query = exclude_disabled_accounts(query)

    if direction == "expense":
        query = query.where(Transaction.amount < 0)
    elif direction == "income":
        query = query.where(Transaction.amount > 0)

    query = query.order_by(Transaction.posted_at)

    result = await db.execute(query)
    rows = result.all()

    # Group by (normalized_description, account_id)
    groups: dict[tuple[str, str], list[tuple[Transaction, str]]] = defaultdict(list)
    for row in rows:
        tx = row[0]
        acct_name = row[1]
        norm = normalize_description(tx.description)
        groups[(norm, tx.account_id)].append((tx, acct_name))

    patterns: list[RecurringPattern] = []

    for (norm_desc, acct_id), txns in groups.items():
        if len(txns) < 3:
            continue

        # Compute intervals between consecutive transactions
        timestamps = [tx.posted_at for tx, _ in txns]
        intervals_days = [
            (timestamps[i + 1] - timestamps[i]) / 86400
            for i in range(len(timestamps) - 1)
        ]

        if not intervals_days:
            continue

        median_interval = statistics.median(intervals_days)
        frequency = _classify_frequency(median_interval)
        if frequency is None:
            continue

        # Check regularity
        if len(intervals_days) >= 2:
            std_dev = statistics.stdev(intervals_days)
        else:
            std_dev = 0.0

        if std_dev > _max_std_dev(frequency):
            continue

        # Compute confidence
        confidence = (
            max(0.0, min(1.0, 1.0 - (std_dev / median_interval)))
            if median_interval > 0
            else 0.0
        )

        # Predict next occurrence
        last_ts = timestamps[-1]
        predicted_next = last_ts + int(median_interval * 86400)

        # Median amount (absolute)
        amounts = [abs(tx.amount) for tx, _ in txns]
        median_amount = int(statistics.median(amounts))

        # Most recent raw description and account name
        last_tx, acct_name = txns[-1]

        patterns.append(
            RecurringPattern(
                description=norm_desc,
                raw_description=last_tx.description,
                account_id=acct_id,
                account_name=acct_name,
                frequency=frequency,
                median_amount=median_amount,
                last_occurrence=last_ts,
                predicted_next=predicted_next,
                occurrence_count=len(txns),
                confidence=confidence,
            )
        )

    # Sort by predicted_next ascending
    patterns.sort(key=lambda p: p.predicted_next)
    return patterns
