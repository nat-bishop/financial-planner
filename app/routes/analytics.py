import time

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Transaction
from app.schemas import SpendingByCategory, SpendingByCategoryResponse

router = APIRouter()


@router.get("/spending-by-category", response_model=SpendingByCategoryResponse)
async def spending_by_category(
    start_date: int | None = None,
    end_date: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> SpendingByCategoryResponse:
    """Get spending totals grouped by category.

    Args:
        start_date: Filter by posted_at >= start_date (Unix timestamp, default: 30 days ago)
        end_date: Filter by posted_at <= end_date (Unix timestamp, default: now)

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

    result = await db.execute(query)
    rows = result.all()

    categories = [
        SpendingByCategory(
            category=row.category,
            total=abs(row.total),  # Return as positive for readability
            count=row.count,
        )
        for row in rows
    ]

    return SpendingByCategoryResponse(
        start_date=start_date,
        end_date=end_date,
        categories=categories,
    )
