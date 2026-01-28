import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Transaction
from app.schemas import TransactionResponse, TransactionUpdate

router = APIRouter()


@router.get("/", response_model=list[TransactionResponse])
async def list_transactions(
    account_id: str | None = None,
    category: str | None = None,
    start_date: int | None = None,
    end_date: int | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[Transaction]:
    """List transactions with optional filters.

    Args:
        account_id: Filter by account ID
        category: Filter by category
        start_date: Filter by posted_at >= start_date (Unix timestamp)
        end_date: Filter by posted_at <= end_date (Unix timestamp)
        limit: Maximum number of results (default 100)
        offset: Number of results to skip (default 0)
    """
    query = select(Transaction).order_by(Transaction.posted_at.desc())

    if account_id:
        query = query.where(Transaction.account_id == account_id)
    if category:
        query = query.where(Transaction.category == category)
    if start_date is not None:
        query = query.where(Transaction.posted_at >= start_date)
    if end_date is not None:
        query = query.where(Transaction.posted_at <= end_date)

    query = query.offset(offset).limit(limit)

    result = await db.scalars(query)
    return list(result.all())


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: int,
    db: AsyncSession = Depends(get_db),
) -> Transaction:
    """Get a specific transaction by ID."""
    transaction = await db.get(Transaction, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction


@router.patch("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: int,
    update: TransactionUpdate,
    db: AsyncSession = Depends(get_db),
) -> Transaction:
    """Update transaction metadata (category, tags, notes).

    Only the fields provided in the request body will be updated.
    """
    transaction = await db.get(Transaction, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    update_data = update.model_dump(exclude_unset=True)
    if update_data:
        for field, value in update_data.items():
            setattr(transaction, field, value)
        transaction.updated_at = int(time.time())

    return transaction
