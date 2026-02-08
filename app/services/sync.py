"""Sync orchestration for SimpleFIN data."""

import asyncio
import json
import logging
import time

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.simplefin import SFAccount, SFTransaction, SimpleFINClient
from app.core.encryption import decrypt
from app.models import Account, Credential, SyncLog, Transaction

log = logging.getLogger(__name__)

_sync_lock = asyncio.Lock()

# SimpleFIN allows ~24 requests per day.
MAX_SYNCS_PER_DAY = 24
_ONE_DAY = 86400


async def get_credential(db: AsyncSession) -> Credential | None:
    """Get SimpleFIN credential from database."""
    return await db.scalar(
        select(Credential).where(Credential.provider == "simplefin")
    )


async def sync_accounts(db: AsyncSession) -> SyncLog:
    """Sync accounts and transactions from SimpleFIN.

    Returns:
        SyncLog with results

    Raises:
        RuntimeError: If a sync is already in progress or daily limit reached
    """
    if _sync_lock.locked():
        raise RuntimeError("Sync already in progress")

    # Rate limit: max 24 successful syncs per rolling 24-hour window
    now = int(time.time())
    day_ago = now - _ONE_DAY
    sync_count = await db.scalar(
        select(func.count())
        .select_from(SyncLog)
        .where(SyncLog.status == "success", SyncLog.completed_at >= day_ago)
    )
    if sync_count and sync_count >= MAX_SYNCS_PER_DAY:
        raise RuntimeError(
            f"Daily limit reached — {MAX_SYNCS_PER_DAY} syncs in the last 24 hours. "
            f"SimpleFIN allows ~24 requests/day."
        )

    async with _sync_lock:
        return await _sync_accounts_inner(db)


async def _sync_accounts_inner(db: AsyncSession) -> SyncLog:
    now = int(time.time())

    # Create sync log entry
    sync_log = SyncLog(started_at=now, status="running")
    db.add(sync_log)
    await db.flush()

    log.info("Sync started")

    try:
        credential = await get_credential(db)
        if not credential:
            log.warning("Sync failed: no credentials configured")
            sync_log.status = "failed"
            sync_log.error_message = "No SimpleFIN credentials configured"
            sync_log.completed_at = int(time.time())
            return sync_log

        # Decrypt access URL
        cred_data = json.loads(decrypt(credential.encrypted_data))
        access_url = cred_data["access_url"]

        client = SimpleFINClient(access_url)

        # Compute date range: cursor (last sync timestamp) to now
        start_date = None
        if credential.sync_cursor:
            start_date = int(credential.sync_cursor)
        # else: first sync — client defaults to 60 days ago

        response = await client.fetch_accounts(
            start_date=start_date,
            end_date=now,
        )

        # Log any errors from SimpleFIN (rate limits, warnings)
        if response.errors:
            for err in response.errors:
                log.warning("SimpleFIN error: %s", err)
            sync_log.error_message = "; ".join(response.errors)

        accounts_synced = set()
        transactions_added = 0

        # Upsert accounts
        for account in response.accounts:
            await _upsert_account(db, account)
            accounts_synced.add(account.id)

        # Upsert transactions
        for tx in response.transactions:
            await _upsert_transaction(db, tx)
            transactions_added += 1

        # Save cursor as current timestamp
        credential.sync_cursor = str(now)
        await db.flush()

        sync_log.accounts_synced = len(accounts_synced)
        sync_log.transactions_added = transactions_added
        sync_log.status = "success"
        sync_log.completed_at = int(time.time())
        sync_log.raw_response = response.raw_json

        log.info(
            "Sync complete: %d accounts, %d transactions",
            len(accounts_synced),
            transactions_added,
        )

    except Exception as e:
        log.error("Sync failed: %s", e)
        sync_log.status = "failed"
        sync_log.error_message = str(e)
        sync_log.completed_at = int(time.time())
        await db.commit()  # Ensure failure is recorded before re-raising
        raise

    return sync_log


async def _upsert_account(db: AsyncSession, account: SFAccount) -> None:
    """Insert or update an account from SimpleFIN data."""
    now = int(time.time())

    stmt = insert(Account).values(
        id=account.id,
        provider="simplefin",
        org_name=account.org_name,
        name=account.name,
        account_type=None,
        currency=account.currency,
        balance_current=account.balance_current,
        balance_available=account.balance_available,
        balance_date=account.balance_date or now,
        last_synced_at=now,
        created_at=now,
    )

    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            "org_name": stmt.excluded.org_name,
            "name": stmt.excluded.name,
            "balance_current": stmt.excluded.balance_current,
            "balance_available": stmt.excluded.balance_available,
            "balance_date": stmt.excluded.balance_date,
            "last_synced_at": stmt.excluded.last_synced_at,
        },
    )

    await db.execute(stmt)


async def _upsert_transaction(db: AsyncSession, tx: SFTransaction) -> None:
    """Insert or update a transaction from SimpleFIN data.

    On conflict, core fields (amount, description, pending status) are updated
    but user-managed fields (category, tags, notes) are preserved.
    """
    now = int(time.time())

    stmt = insert(Transaction).values(
        account_id=tx.account_id,
        external_id=tx.id,
        posted_at=tx.date,
        amount=tx.amount,
        description=tx.description,
        is_pending=tx.pending,
        raw_data=json.dumps({
            "simplefin_id": tx.id,
            "pending": tx.pending,
        }),
        created_at=now,
    )

    # On conflict, update core fields but preserve user-managed fields
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
