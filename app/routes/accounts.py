from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Account
from app.schemas import AccountResponse, AccountUpdate

router = APIRouter()


@router.get("/", response_model=list[AccountResponse])
async def list_accounts(
    include_disabled: bool = Query(default=False),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[Account]:
    """List all synced accounts."""
    query = select(Account).order_by(Account.name)
    if not include_disabled:
        query = query.where(Account.is_disabled == False)  # noqa: E712
    result = await db.scalars(query.offset(offset).limit(limit))
    return list(result.all())


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: str,
    update: AccountUpdate,
    db: AsyncSession = Depends(get_db),
) -> Account:
    """Update account settings (e.g., disable/enable)."""
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(account, field, value)

    return account
