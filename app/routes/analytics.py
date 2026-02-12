import calendar
import json
import logging
import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Category, Transaction, UserSetting, exclude_disabled_accounts
from app.schemas import (
    IncomeProjectionResponse,
    IncomeSource,
    MonthlyBucket,
    MonthlyTrendResponse,
    ProjectionBand,
    ProjectionPoint,
    RecurringBill,
    RecurringBillsResponse,
    SpendingByCategory,
    SpendingByCategoryResponse,
)
from app.services.recurring import detect_recurring

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/monthly-trend", response_model=MonthlyTrendResponse)
async def monthly_trend(
    months: int = Query(default=12, ge=1, le=60),
    include_excluded: bool = False,
    db: AsyncSession = Depends(get_db),
) -> MonthlyTrendResponse:
    """Get monthly income and expense totals.

    Returns one bucket per month with income, expenses, and net amounts.
    """
    now = int(time.time())
    start_ts = now - (months * 30 * 24 * 60 * 60)

    month_col = func.strftime("%Y-%m", Transaction.posted_at, "unixepoch")

    query = (
        select(
            month_col.label("month"),
            func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)).label(
                "income"
            ),
            func.sum(
                case((Transaction.amount < 0, -Transaction.amount), else_=0)
            ).label("expenses"),
            func.count(Transaction.id).label("tx_count"),
        )
        .where(Transaction.posted_at >= start_ts)
        .group_by(month_col)
        .order_by(month_col)
    )
    query = exclude_disabled_accounts(query)

    if not include_excluded:
        excluded_names = select(Category.name).where(
            Category.exclude_from_totals == True  # noqa: E712
        )
        query = query.where(Transaction.category.notin_(excluded_names))

    result = await db.execute(query)
    rows = result.all()

    buckets = []
    for row in rows:
        year, mon = row.month.split("-")
        month_start = calendar.timegm(time.strptime(f"{year}-{mon}-01", "%Y-%m-%d"))
        income = row.income or 0
        expenses = row.expenses or 0
        buckets.append(
            MonthlyBucket(
                month=row.month,
                month_start=month_start,
                income=income,
                expenses=expenses,
                net=income - expenses,
                transaction_count=row.tx_count,
            )
        )

    return MonthlyTrendResponse(months=buckets)


@router.get("/spending-by-category", response_model=SpendingByCategoryResponse)
async def spending_by_category(
    start_date: int | None = None,
    end_date: int | None = None,
    include_excluded: bool = False,
    db: AsyncSession = Depends(get_db),
) -> SpendingByCategoryResponse:
    """Get spending totals grouped by category.

    Args:
        start_date: Filter by posted_at >= start_date (Unix timestamp, default: 30 days ago)
        end_date: Filter by posted_at <= end_date (Unix timestamp, default: now)
        include_excluded: If True, include categories marked exclude_from_totals (default: False)

    Returns:
        Spending totals by category (only includes negative amounts / expenses)
    """
    now = int(time.time())

    if start_date is None:
        start_date = now - (30 * 24 * 60 * 60)  # 30 days ago
    if end_date is None:
        end_date = now

    query = (
        select(
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .where(Transaction.posted_at >= start_date)
        .where(Transaction.posted_at <= end_date)
        .where(Transaction.amount < 0)  # Only expenses
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount))  # Most spending first
    )
    query = exclude_disabled_accounts(query)

    if not include_excluded:
        excluded_names = select(Category.name).where(
            Category.exclude_from_totals == True  # noqa: E712
        )
        query = query.where(Transaction.category.notin_(excluded_names))

    result = await db.execute(query)
    rows = result.all()

    # Build lookup of excluded category names (only needed when including excluded)
    excluded_set: set[str] = set()
    if include_excluded:
        excluded_result = await db.scalars(
            select(Category.name).where(Category.exclude_from_totals == True)  # noqa: E712
        )
        excluded_set = set(excluded_result.all())

    categories = [
        SpendingByCategory(
            category=row.category,
            total=abs(row.total),  # Return as positive for readability
            count=row.count,
            exclude_from_totals=row.category in excluded_set,
        )
        for row in rows
    ]

    return SpendingByCategoryResponse(
        start_date=start_date,
        end_date=end_date,
        categories=categories,
    )


@router.get("/recurring-bills", response_model=RecurringBillsResponse)
async def recurring_bills(
    lookback_months: int = Query(default=6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
) -> RecurringBillsResponse:
    """Detect recurring bills from transaction patterns."""
    patterns = await detect_recurring(
        db, lookback_months=lookback_months, direction="expense"
    )

    bills = [
        RecurringBill(
            description=p.description,
            raw_description=p.raw_description,
            account_id=p.account_id,
            account_name=p.account_name,
            frequency=p.frequency,
            median_amount=p.median_amount,
            last_occurrence=p.last_occurrence,
            predicted_next=p.predicted_next,
            occurrence_count=p.occurrence_count,
            confidence=p.confidence,
        )
        for p in patterns
    ]

    return RecurringBillsResponse(bills=bills, lookback_months=lookback_months)


# Default S&P 500 historical return bands
_DEFAULT_RETURNS = {"low": 0.04, "average": 0.10, "high": 0.14}


def _compute_projection(
    monthly_contribution: int,
    years: int,
    annual_returns: dict[str, float],
) -> list[ProjectionBand]:
    """Compute compound growth with monthly contributions for each return band."""
    bands = []
    for label, rate in annual_returns.items():
        monthly_rate = (1 + rate) ** (1 / 12) - 1
        balance = 0
        points = [ProjectionPoint(year=0, balance=0, contributions=0)]
        for month in range(1, years * 12 + 1):
            balance = int(balance * (1 + monthly_rate)) + monthly_contribution
            if month % 12 == 0:
                points.append(
                    ProjectionPoint(
                        year=month // 12,
                        balance=balance,
                        contributions=monthly_contribution * month,
                    )
                )
        pct = int(rate * 100)
        bands.append(
            ProjectionBand(
                label=f"{label.title()} ({pct}%)",
                annual_return=rate,
                points=points,
            )
        )
    return bands


@router.get("/income-projection", response_model=IncomeProjectionResponse)
async def income_projection(
    time_horizon_years: int = Query(default=30, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> IncomeProjectionResponse:
    """Compute income projection with investment growth bands.

    Uses configured income sources if available, otherwise auto-detects
    recurring income and expenses from transaction history.
    """
    is_configured = False
    income_sources: list[IncomeSource] = []
    monthly_contribution_override: int | None = None
    return_rates = dict(_DEFAULT_RETURNS)

    # Check for user configuration
    for key_name in (
        "projection_income_sources",
        "projection_monthly_contribution",
        "projection_return_rates",
    ):
        setting = await db.get(UserSetting, key_name)
        if setting:
            is_configured = True
            try:
                val = json.loads(setting.value)
                if key_name == "projection_income_sources":
                    income_sources = [IncomeSource(**s) for s in val]
                elif key_name == "projection_monthly_contribution":
                    monthly_contribution_override = val
                elif key_name == "projection_return_rates":
                    return_rates.update(val)
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                log.warning("Malformed setting %s: %s", key_name, e)

    # Auto-calculate income and expenses
    if income_sources:
        monthly_income = sum(s.monthly_amount for s in income_sources)
    else:
        # Try recurring income detection first
        recurring_income = await detect_recurring(
            db, lookback_months=6, direction="income"
        )
        if recurring_income:
            monthly_income = 0
            for p in recurring_income:
                if p.frequency == "monthly":
                    monthly_amt = p.median_amount
                elif p.frequency == "biweekly":
                    monthly_amt = int(p.median_amount * 26 / 12)
                elif p.frequency == "weekly":
                    monthly_amt = int(p.median_amount * 52 / 12)
                else:
                    continue
                monthly_income += monthly_amt
                income_sources.append(
                    IncomeSource(name=p.raw_description, monthly_amount=monthly_amt)
                )
        else:
            # Fallback: average positive amounts over last 3 months
            now = int(time.time())
            three_months_ago = now - (90 * 24 * 60 * 60)
            income_query = (
                select(func.sum(Transaction.amount))
                .where(Transaction.amount > 0)
                .where(Transaction.posted_at >= three_months_ago)
            )
            income_query = exclude_disabled_accounts(income_query)
            result = await db.execute(income_query)
            total_income = result.scalar() or 0
            monthly_income = total_income // 3

    # Calculate expenses
    now = int(time.time())
    three_months_ago = now - (90 * 24 * 60 * 60)
    expense_query = (
        select(func.sum(Transaction.amount))
        .where(Transaction.amount < 0)
        .where(Transaction.posted_at >= three_months_ago)
    )
    expense_query = exclude_disabled_accounts(expense_query)
    result = await db.execute(expense_query)
    total_expenses = abs(result.scalar() or 0)
    monthly_expenses = total_expenses // 3

    # Monthly contribution
    if monthly_contribution_override is not None:
        monthly_contribution = monthly_contribution_override
    else:
        monthly_contribution = max(0, monthly_income - monthly_expenses)

    # Compute projection bands
    bands = _compute_projection(monthly_contribution, time_horizon_years, return_rates)

    return IncomeProjectionResponse(
        monthly_income=monthly_income,
        monthly_expenses=monthly_expenses,
        monthly_contribution=monthly_contribution,
        income_sources=income_sources,
        bands=bands,
        time_horizon_years=time_horizon_years,
        is_configured=is_configured,
    )
