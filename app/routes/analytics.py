import calendar
import json
import logging
import time
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import (
    Account,
    Category,
    Transaction,
    UserSetting,
    exclude_disabled_accounts,
)
from app.schemas import (
    IncomeProjectionResponse,
    IncomeSource,
    MonthlyBucket,
    MonthlyTrendResponse,
    NetWorthHistoryResponse,
    NetWorthPoint,
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

# Multipliers to annualize different pay frequencies to monthly
_FREQUENCY_TO_MONTHLY: dict[str, float] = {
    "monthly": 1.0,
    "biweekly": 26 / 12,
    "weekly": 52 / 12,
}

# Default S&P 500 historical return bands
_DEFAULT_RETURNS = {"low": 0.04, "average": 0.10, "high": 0.14}


def _exclude_categories(query):
    """Filter out transactions whose category is marked exclude_from_totals."""
    excluded = select(Category.name).where(
        Category.exclude_from_totals == True  # noqa: E712
    )
    return query.where(Transaction.category.notin_(excluded))


async def _avg_monthly_amount(
    db: AsyncSession, *, positive: bool, months: int = 3
) -> int:
    """Average monthly income or expense over the last N months."""
    cutoff = int(time.time()) - (months * 30 * 24 * 60 * 60)
    condition = Transaction.amount > 0 if positive else Transaction.amount < 0
    query = (
        select(func.sum(Transaction.amount))
        .where(condition)
        .where(Transaction.posted_at >= cutoff)
    )
    query = exclude_disabled_accounts(query)
    result = await db.execute(query)
    total = abs(result.scalar() or 0)
    return total // months


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/monthly-trend", response_model=MonthlyTrendResponse)
async def monthly_trend(
    months: int = Query(default=12, ge=1, le=60),
    include_excluded: bool = False,
    db: AsyncSession = Depends(get_db),
) -> MonthlyTrendResponse:
    """Get monthly income and expense totals."""
    start_ts = int(time.time()) - (months * 30 * 24 * 60 * 60)
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
        query = _exclude_categories(query)

    rows = (await db.execute(query)).all()

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
    """Get spending totals grouped by category."""
    now = int(time.time())
    if start_date is None:
        start_date = now - (30 * 24 * 60 * 60)
    if end_date is None:
        end_date = now

    query = (
        select(
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("cnt"),
        )
        .where(Transaction.posted_at >= start_date)
        .where(Transaction.posted_at <= end_date)
        .where(Transaction.amount < 0)
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount))
    )
    query = exclude_disabled_accounts(query)
    if not include_excluded:
        query = _exclude_categories(query)

    rows = (await db.execute(query)).all()

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
            total=abs(row.total),
            count=row.cnt,
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
    bills = [RecurringBill(**asdict(p)) for p in patterns]
    return RecurringBillsResponse(bills=bills, lookback_months=lookback_months)


@router.get("/net-worth-history", response_model=NetWorthHistoryResponse)
async def net_worth_history(
    months_back: int = Query(default=24, ge=1, le=60),
    months_forward: int = Query(default=12, ge=0, le=36),
    db: AsyncSession = Depends(get_db),
) -> NetWorthHistoryResponse:
    """Compute net worth history by walking backwards from current balance.

    Also projects forward using recent average monthly net.
    """
    # Current total balance across enabled accounts
    result = await db.execute(
        select(func.sum(Account.balance_current)).where(
            Account.is_disabled == False  # noqa: E712
        )
    )
    current_balance = result.scalar() or 0

    # Get monthly trend data for lookback period
    trend_resp = await monthly_trend(months=months_back, include_excluded=False, db=db)
    trend_months = trend_resp.months

    # Build historical points by walking backwards from current balance
    # Start from current month and go back
    now_ts = int(time.time())
    now_year, now_month = time.gmtime(now_ts).tm_year, time.gmtime(now_ts).tm_mon
    current_month_str = f"{now_year}-{now_month:02d}"

    historical: list[NetWorthPoint] = []
    running_balance = current_balance

    # Create a lookup of net by month
    net_by_month: dict[str, int] = {}
    for bucket in trend_months:
        net_by_month[bucket.month] = bucket.net

    # Current month first
    historical.append(NetWorthPoint(month=current_month_str, balance=running_balance))

    # Walk backwards
    year, month = now_year, now_month
    for _ in range(months_back):
        # Go to previous month
        month -= 1
        if month == 0:
            month = 12
            year -= 1
        month_str = f"{year}-{month:02d}"
        net = net_by_month.get(month_str, 0)
        # Previous balance = current - net for that month
        running_balance -= net
        historical.append(NetWorthPoint(month=month_str, balance=running_balance))

    historical.reverse()
    today_index = len(historical) - 1

    # Monthly averages from last 3 months for projection
    monthly_income = await _avg_monthly_amount(db, positive=True, months=3)
    monthly_expenses = await _avg_monthly_amount(db, positive=False, months=3)
    monthly_net = monthly_income - monthly_expenses

    # Project forward
    projected_balance = current_balance
    year, month = now_year, now_month
    for _ in range(months_forward):
        month += 1
        if month == 13:
            month = 1
            year += 1
        projected_balance += monthly_net
        historical.append(
            NetWorthPoint(
                month=f"{year}-{month:02d}",
                balance=projected_balance,
            )
        )

    return NetWorthHistoryResponse(
        points=historical,
        today_index=today_index,
        monthly_income=monthly_income,
        monthly_expenses=monthly_expenses,
        monthly_net=monthly_net,
    )


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


async def _load_projection_settings(
    db: AsyncSession,
) -> tuple[bool, list[IncomeSource], int | None, dict[str, float]]:
    """Load user-configured projection settings.

    Returns (is_configured, income_sources, contribution_override, return_rates).
    """
    is_configured = False
    income_sources: list[IncomeSource] = []
    contribution_override: int | None = None
    return_rates = dict(_DEFAULT_RETURNS)

    parsers: dict[str, type] = {
        "projection_income_sources": list,
        "projection_monthly_contribution": int,
        "projection_return_rates": dict,
    }

    for key in parsers:
        setting = await db.get(UserSetting, key)
        if not setting:
            continue
        is_configured = True
        try:
            val = json.loads(setting.value)
            if key == "projection_income_sources":
                income_sources = [IncomeSource(**s) for s in val]
            elif key == "projection_monthly_contribution":
                contribution_override = val
            elif key == "projection_return_rates":
                return_rates.update(val)
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            log.warning("Malformed setting %s: %s", key, e)

    return is_configured, income_sources, contribution_override, return_rates


async def _detect_monthly_income(
    db: AsyncSession,
) -> tuple[int, list[IncomeSource]]:
    """Auto-detect monthly income from recurring patterns or 3-month average."""
    recurring = await detect_recurring(db, lookback_months=6, direction="income")
    if recurring:
        sources: list[IncomeSource] = []
        for p in recurring:
            multiplier = _FREQUENCY_TO_MONTHLY.get(p.frequency)
            if multiplier is None:
                continue
            monthly_amt = int(p.median_amount * multiplier)
            sources.append(
                IncomeSource(name=p.raw_description, monthly_amount=monthly_amt)
            )
        return sum(s.monthly_amount for s in sources), sources

    # Fallback: 3-month average
    avg = await _avg_monthly_amount(db, positive=True, months=3)
    return avg, []


@router.get("/income-projection", response_model=IncomeProjectionResponse)
async def income_projection(
    time_horizon_years: int = Query(default=30, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> IncomeProjectionResponse:
    """Compute income projection with investment growth bands."""
    (
        is_configured,
        income_sources,
        contribution_override,
        return_rates,
    ) = await _load_projection_settings(db)

    # Determine monthly income
    if income_sources:
        monthly_income = sum(s.monthly_amount for s in income_sources)
    else:
        monthly_income, income_sources = await _detect_monthly_income(db)

    # Determine monthly expenses (3-month average)
    monthly_expenses = await _avg_monthly_amount(db, positive=False, months=3)

    # Monthly contribution
    monthly_contribution = (
        contribution_override
        if contribution_override is not None
        else max(0, monthly_income - monthly_expenses)
    )

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
