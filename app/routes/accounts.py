from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Account
from app.schemas import AccountResponse

router = APIRouter()


@router.get("/", response_model=list[AccountResponse])
async def list_accounts(db: AsyncSession = Depends(get_db)) -> list[Account]:
    """List all synced accounts."""
    result = await db.scalars(select(Account).order_by(Account.name))
    return list(result.all())


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: str,
    db: AsyncSession = Depends(get_db),
) -> Account:
    """Get a specific account by ID."""
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account
