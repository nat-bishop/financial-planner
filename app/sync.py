"""Sync orchestration for SimpleFIN data."""

import json
import time

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption import decrypt
from app.models import Account, Credential, SyncLog, Transaction
from app.simplefin import SimpleFINClient, _to_cents


async def get_simplefin_client(db: AsyncSession) -> SimpleFINClient | None:
    """Get SimpleFIN client from stored credentials."""
    credential = await db.scalar(
        select(Credential).where(Credential.provider == "simplefin")
    )
    if not credential:
        return None

    cred_data = json.loads(decrypt(credential.encrypted_data))
    return SimpleFINClient(cred_data["access_url"])


async def sync_accounts(
    db: AsyncSession, start_date: int | None = None, end_date: int | None = None
) -> SyncLog:
    """Sync accounts and transactions from SimpleFIN.

    Args:
        db: Database session
        start_date: Unix timestamp for transaction start date (default: 60 days ago)
        end_date: Unix timestamp for transaction end date (default: now)

    Returns:
        SyncLog with results
    """
    now = int(time.time())

    # Default to 60-day window (SimpleFIN's max)
    if start_date is None:
        start_date = now - (60 * 24 * 60 * 60)
    if end_date is None:
        end_date = now

    # Create sync log entry
    sync_log = SyncLog(started_at=now, status="running")
    db.add(sync_log)
    await db.flush()

    try:
        client = await get_simplefin_client(db)
        if not client:
            sync_log.status = "failed"
            sync_log.error_message = "No SimpleFIN credentials configured"
            sync_log.completed_at = int(time.time())
            return sync_log

        # Fetch data from SimpleFIN
        response = await client.fetch_accounts(start_date=start_date, end_date=end_date)
        sync_log.raw_response = response.raw_json

        transactions_added = 0
        transactions_updated = 0

        for sf_account in response.accounts:
            # Upsert account
            await _upsert_account(db, sf_account)

            # Upsert transactions
            for tx in sf_account.transactions:
                was_updated = await _upsert_transaction(db, sf_account.id, tx)
                if was_updated:
                    transactions_updated += 1
                else:
                    transactions_added += 1

        sync_log.accounts_synced = len(response.accounts)
        sync_log.transactions_added = transactions_added
        sync_log.transactions_updated = transactions_updated
        sync_log.status = "success"
        sync_log.completed_at = int(time.time())

    except Exception as e:
        sync_log.status = "failed"
        sync_log.error_message = str(e)
        sync_log.completed_at = int(time.time())
        raise

    return sync_log


async def _upsert_account(db: AsyncSession, sf_account) -> None:
    """Insert or update an account from SimpleFIN data."""
    now = int(time.time())

    stmt = insert(Account).values(
        id=sf_account.id,
        provider="simplefin",
        org_domain=sf_account.org_domain,
        org_name=sf_account.org_name,
        name=sf_account.name,
        currency=sf_account.currency,
        balance_current=sf_account.balance,
        balance_available=sf_account.available_balance,
        balance_date=sf_account.balance_date,
        last_synced_at=now,
        created_at=now,
    )

    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            "org_domain": stmt.excluded.org_domain,
            "org_name": stmt.excluded.org_name,
            "name": stmt.excluded.name,
            "balance_current": stmt.excluded.balance_current,
            "balance_available": stmt.excluded.balance_available,
            "balance_date": stmt.excluded.balance_date,
            "last_synced_at": stmt.excluded.last_synced_at,
        },
    )

    await db.execute(stmt)


async def _upsert_transaction(db: AsyncSession, account_id: str, tx: dict) -> bool:
    """Insert or update a transaction from SimpleFIN data.

    Returns True if the transaction was updated (existed), False if it was inserted (new).
    """
    now = int(time.time())

    # SimpleFIN transaction format
    external_id = tx.get("id")
    posted_at = tx.get("posted", 0)
    amount = _to_cents(tx.get("amount", 0))
    description = tx.get("description", "")
    is_pending = tx.get("pending", False)

    # Check if transaction exists
    existing = await db.scalar(
        select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.external_id == external_id,
        )
    )

    stmt = insert(Transaction).values(
        account_id=account_id,
        external_id=external_id,
        posted_at=posted_at,
        amount=amount,
        description=description,
        is_pending=is_pending,
        raw_data=json.dumps(tx),
        created_at=now,
    )

    stmt = stmt.on_conflict_do_update(
        index_elements=["account_id", "external_id"],
        set_={
            "posted_at": stmt.excluded.posted_at,
            "amount": stmt.excluded.amount,
            "description": stmt.excluded.description,
            "is_pending": stmt.excluded.is_pending,
            "raw_data": stmt.excluded.raw_data,
            "updated_at": now,
        },
    )

    await db.execute(stmt)
    return existing is not None
