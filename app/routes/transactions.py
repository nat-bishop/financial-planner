import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import (
    Account,
    CategoryMemory,
    Transaction,
    exclude_disabled_accounts,
    normalize_description,
)
from app.schemas import (
    TransactionIdsResponse,
    TransactionListResponse,
    TransactionResponse,
    TransactionUpdate,
)

router = APIRouter()


def _build_filters(
    query,
    account_id: str | None = None,
    category: str | None = None,
    search: str | None = None,
    start_date: int | None = None,
    end_date: int | None = None,
):
    """Apply shared filter conditions to a Transaction query."""
    query = exclude_disabled_accounts(query)

    if account_id:
        query = query.where(Transaction.account_id == account_id)
    if category:
        query = query.where(Transaction.category == category)
    if search:
        query = query.where(Transaction.description.ilike(f"%{search}%"))
    if start_date is not None:
        query = query.where(Transaction.posted_at >= start_date)
    if end_date is not None:
        query = query.where(Transaction.posted_at <= end_date)

    return query


@router.get("/", response_model=TransactionListResponse)
async def list_transactions(
    account_id: str | None = None,
    category: str | None = None,
    search: str | None = None,
    start_date: int | None = None,
    end_date: int | None = None,
    sort_by: Literal["date", "description", "category", "amount", "account"] = "date",
    sort_order: Literal["asc", "desc"] = "desc",
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List transactions with optional filters, sorting, and aggregates."""
    # Data query
    data_query = select(Transaction)
    data_query = _build_filters(
        data_query, account_id, category, search, start_date, end_date
    )

    # Sorting
    sort_map = {
        "date": Transaction.posted_at,
        "description": Transaction.description,
        "category": Transaction.category,
        "amount": Transaction.amount,
    }
    if sort_by == "account":
        data_query = data_query.join(Account, Transaction.account_id == Account.id)
        sort_col = Account.name
    else:
        sort_col = sort_map[sort_by]

    if sort_order == "asc":
        data_query = data_query.order_by(sort_col.asc())
    else:
        data_query = data_query.order_by(sort_col.desc())

    data_query = data_query.offset(offset).limit(limit)

    # Aggregate query (same filters, no limit/offset)
    agg_query = select(
        func.count(Transaction.id).label("total_count"),
        func.coalesce(
            func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)), 0
        ).label("total_income"),
        func.coalesce(
            func.sum(case((Transaction.amount < 0, -Transaction.amount), else_=0)), 0
        ).label("total_expenses"),
    )
    agg_query = _build_filters(
        agg_query, account_id, category, search, start_date, end_date
    )

    # Execute both
    result = await db.scalars(data_query)
    transactions = list(result.all())

    agg_result = (await db.execute(agg_query)).one()

    return {
        "transactions": transactions,
        "total_count": agg_result.total_count,
        "total_income": agg_result.total_income,
        "total_expenses": agg_result.total_expenses,
    }


@router.get("/ids", response_model=TransactionIdsResponse)
async def list_transaction_ids(
    account_id: str | None = None,
    category: str | None = None,
    search: str | None = None,
    start_date: int | None = None,
    end_date: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Return all matching transaction IDs (no pagination)."""
    query = select(Transaction.id)
    query = _build_filters(query, account_id, category, search, start_date, end_date)

    result = await db.scalars(query)
    return {"ids": list(result.all())}


@router.patch("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: int,
    update: TransactionUpdate,
    db: AsyncSession = Depends(get_db),
) -> Transaction:
    """Update transaction metadata (category, tags, notes).

    Only the fields provided in the request body will be updated.
    When category is changed, updates category_memory for future auto-matching.
    """
    transaction = await db.get(Transaction, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    update_data = update.model_dump(exclude_unset=True)
    if update_data:
        category_changed = "category" in update_data
        new_category = update_data.get("category")

        for field, value in update_data.items():
            setattr(transaction, field, value)
        transaction.updated_at = int(time.time())

        # On category change: reset confidence and update memory
        if category_changed:
            transaction.categorize_confidence = None
            pattern = normalize_description(transaction.description)

            if new_category == "Uncategorized":
                # Delete memory entry — stop auto-applying this pattern
                await db.execute(
                    delete(CategoryMemory).where(
                        CategoryMemory.normalized_pattern == pattern,
                        CategoryMemory.account_id == transaction.account_id,
                    )
                )
            else:
                # Upsert memory entry — user correction always wins
                now = int(time.time())
                stmt = insert(CategoryMemory).values(
                    normalized_pattern=pattern,
                    account_id=transaction.account_id,
                    category=new_category,
                    created_at=now,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["normalized_pattern", "account_id"],
                    set_={
                        "category": stmt.excluded.category,
                        "updated_at": now,
                    },
                )
                await db.execute(stmt)

    return transaction
