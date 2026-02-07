"""Sync orchestration for Plaid data."""

import json
import time

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption import decrypt
from app.models import Account, Credential, SyncLog, Transaction
from app.plaid import PlaidAccount, PlaidClient, PlaidTransaction


async def get_plaid_credential(db: AsyncSession) -> Credential | None:
    """Get Plaid credential from database."""
    return await db.scalar(select(Credential).where(Credential.provider == "plaid"))


async def sync_accounts(db: AsyncSession) -> SyncLog:
    """Sync accounts and transactions from Plaid.

    Uses cursor-based sync for efficient incremental updates.
    Saves cursor after each page for safe checkpointing.

    Returns:
        SyncLog with results
    """
    now = int(time.time())

    # Create sync log entry
    sync_log = SyncLog(started_at=now, status="running")
    db.add(sync_log)
    await db.flush()

    try:
        credential = await get_plaid_credential(db)
        if not credential:
            sync_log.status = "failed"
            sync_log.error_message = "No Plaid credentials configured"
            sync_log.completed_at = int(time.time())
            return sync_log

        # Decrypt credentials
        cred_data = json.loads(decrypt(credential.encrypted_data))
        access_token = cred_data["access_token"]

        client = PlaidClient()
        cursor = credential.sync_cursor  # None for first sync

        accounts_synced = set()
        transactions_added = 0
        transactions_updated = 0
        transactions_removed = 0
        raw_responses = []

        while True:
            response = await client.sync_transactions(access_token, cursor)
            raw_responses.append(response.raw_json)

            # Upsert accounts
            for account in response.accounts:
                await _upsert_account(db, account)
                accounts_synced.add(account.id)

            # Handle added transactions
            for tx in response.added:
                await _upsert_transaction(db, tx, use_plaid_category=True)
                transactions_added += 1

            # Handle modified transactions (upsert preserves user fields)
            for tx in response.modified:
                await _upsert_transaction(db, tx, use_plaid_category=False)
                transactions_updated += 1

            # Hard delete removed transactions (bank is source of truth)
            for tx_id in response.removed:
                result = await db.execute(
                    delete(Transaction).where(Transaction.external_id == tx_id)
                )
                if result.rowcount > 0:
                    transactions_removed += 1

            # Save cursor after each page (safe checkpoint on partial failure)
            credential.sync_cursor = response.next_cursor
            await db.flush()

            if not response.has_more:
                break

        sync_log.accounts_synced = len(accounts_synced)
        sync_log.transactions_added = transactions_added
        sync_log.transactions_updated = transactions_updated
        sync_log.status = "success"
        sync_log.completed_at = int(time.time())
        sync_log.raw_response = json.dumps(raw_responses)

    except Exception as e:
        sync_log.status = "failed"
        sync_log.error_message = str(e)
        sync_log.completed_at = int(time.time())
        await db.commit()  # Ensure failure is recorded before re-raising
        raise

    return sync_log


async def _upsert_account(db: AsyncSession, account: PlaidAccount) -> None:
    """Insert or update an account from Plaid data."""
    now = int(time.time())

    # Combine type and subtype for account_type (e.g., "depository/checking")
    account_type = account.type
    if account.subtype:
        account_type = f"{account.type}/{account.subtype}"

    stmt = insert(Account).values(
        id=account.id,
        provider="plaid",
        org_domain=None,  # Plaid doesn't provide institution domains
        org_name=account.official_name or account.name,
        name=account.name,
        account_type=account_type,
        currency=account.currency,
        balance_current=account.balance_current,
        balance_available=account.balance_available,
        balance_date=now,
        last_synced_at=now,
        created_at=now,
    )

    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            "org_name": stmt.excluded.org_name,
            "name": stmt.excluded.name,
            "account_type": stmt.excluded.account_type,
            "balance_current": stmt.excluded.balance_current,
            "balance_available": stmt.excluded.balance_available,
            "balance_date": stmt.excluded.balance_date,
            "last_synced_at": stmt.excluded.last_synced_at,
        },
    )

    await db.execute(stmt)


async def _upsert_transaction(
    db: AsyncSession, tx: PlaidTransaction, use_plaid_category: bool = True
) -> None:
    """Insert or update a transaction from Plaid data.

    Args:
        db: Database session
        tx: Plaid transaction data
        use_plaid_category: If True, set category from Plaid for new transactions.
            For modified transactions, this should be False to preserve user-set categories.
    """
    now = int(time.time())

    # For new transactions, include Plaid's category
    values = {
        "account_id": tx.account_id,
        "external_id": tx.id,
        "posted_at": tx.date,
        "amount": tx.amount,
        "description": tx.description,
        "is_pending": tx.pending,
        "raw_data": json.dumps({
            "plaid_id": tx.id,
            "plaid_category": tx.category,
            "pending": tx.pending,
        }),
        "created_at": now,
    }

    if use_plaid_category and tx.category:
        values["category"] = tx.category

    stmt = insert(Transaction).values(**values)

    # On conflict, update core fields but preserve user-managed fields
    update_set = {
        "posted_at": stmt.excluded.posted_at,
        "amount": stmt.excluded.amount,
        "description": stmt.excluded.description,
        "is_pending": stmt.excluded.is_pending,
        "raw_data": stmt.excluded.raw_data,
        "updated_at": now,
    }

    stmt = stmt.on_conflict_do_update(
        index_elements=["account_id", "external_id"],
        set_=update_set,
    )

    await db.execute(stmt)
