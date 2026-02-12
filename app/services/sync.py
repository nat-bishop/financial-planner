"""Provider-agnostic sync orchestration with background tasks.

All syncs run as background asyncio.Tasks so HTTP requests return immediately.
2FA challenges are relayed via TwoFASession to the frontend.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.core.encryption import decrypt, encrypt
from app.models import Account, Credential, SyncLog, Transaction
from app.providers import (
    ProviderError,
    RateLimitError,
    get_provider,
)
from app.providers.base import FinanceProvider, TwoFAHandler
from app.providers.models import ProviderAccount, ProviderTransaction, SyncResult
from app.services.categorize import apply_memory_rules
from app.services.two_fa import (
    TwoFAChallenge,
    TwoFATimeoutError,
    create_session,
    get_session,
    remove_session,
)

log = logging.getLogger(__name__)

_sync_locks: dict[str, asyncio.Lock] = {}
_background_tasks: dict[int, asyncio.Task] = {}
_ONE_DAY = 86400


def _get_lock(provider_name: str) -> asyncio.Lock:
    return _sync_locks.setdefault(provider_name, asyncio.Lock())


async def get_connected_providers(db: AsyncSession) -> list[str]:
    """Return names of providers that have stored credentials."""
    result = await db.scalars(select(Credential.provider))
    return list(result.all())


async def get_credential(db: AsyncSession, provider_name: str = "simplefin") -> Credential | None:
    """Get credential for a provider."""
    return await db.scalar(
        select(Credential).where(Credential.provider == provider_name)
    )


async def start_sync(provider_name: str, db: AsyncSession) -> SyncLog:
    """Start a background sync for a single provider.

    Creates a SyncLog, spawns a background task, and returns immediately.

    Raises:
        RuntimeError: If sync already in progress for this provider.
        RateLimitError: If daily limit reached.
        KeyError: If provider not found.
    """
    provider = get_provider(provider_name)
    lock = _get_lock(provider_name)

    if lock.locked():
        raise RuntimeError(f"Sync already in progress for {provider_name}")

    # Rate limit check (before spawning background task)
    await _check_rate_limit(db, provider)

    # Create SyncLog in the request's DB session
    now = int(time.time())
    sync_log = SyncLog(
        provider=provider_name,
        started_at=now,
        status="running",
    )
    db.add(sync_log)
    await db.flush()
    sync_log_id = sync_log.id

    # Spawn background task
    task = asyncio.create_task(
        _background_sync(provider_name, sync_log_id),
        name=f"sync-{provider_name}-{sync_log_id}",
    )
    _background_tasks[sync_log_id] = task

    # Remove from tracking dict when done
    task.add_done_callback(lambda t: _background_tasks.pop(sync_log_id, None))

    log.info("Background sync started for %s (sync_log=%d)", provider_name, sync_log_id)
    return sync_log


async def start_sync_all(db: AsyncSession) -> list[SyncLog]:
    """Start background syncs for all connected providers.

    Returns list of SyncLogs (one per provider that was started).
    Providers that fail pre-checks (locked, rate-limited) get failed logs.
    """
    connected = await get_connected_providers(db)
    if not connected:
        return []

    sync_logs: list[SyncLog] = []
    for name in connected:
        try:
            sync_log = await start_sync(name, db)
            sync_logs.append(sync_log)
        except (RuntimeError, RateLimitError) as e:
            now = int(time.time())
            failed_log = SyncLog(
                provider=name,
                started_at=now,
                completed_at=now,
                status="failed",
                error_message=str(e),
            )
            db.add(failed_log)
            sync_logs.append(failed_log)

    await db.flush()
    return sync_logs


async def _background_sync(provider_name: str, sync_log_id: int) -> None:
    """Background task that runs a provider sync with its own DB session.

    Handles locking, timeouts, 2FA relay, and error recovery.

    Uses asyncio.wait instead of wait_for because Playwright coroutines
    don't respond to CancelledError, causing wait_for to hang forever.
    """
    provider = get_provider(provider_name)
    lock = _get_lock(provider_name)

    # Determine timeout: 600s for browser (300s sync + 300s 2FA buffer), 30s for API
    from app.providers.browser import BrowserProvider
    timeout = 600 if isinstance(provider, BrowserProvider) else 30

    async with async_session_maker() as db:
        try:
            async with lock:
                sync_log = await db.get(SyncLog, sync_log_id)
                if not sync_log:
                    log.error("SyncLog %d not found", sync_log_id)
                    return

                # Build 2FA handler closure
                handler = _build_2fa_handler(db, sync_log, provider_name)

                sync_task = asyncio.create_task(
                    _run_sync(db, provider, sync_log, two_fa_handler=handler),
                    name=f"run-sync-{provider_name}",
                )
                done, _ = await asyncio.wait({sync_task}, timeout=timeout)

                if sync_task in done:
                    # Task completed — re-raise any exception
                    exc = sync_task.exception()
                    if exc is not None:
                        if isinstance(exc, TwoFATimeoutError):
                            _fail_sync_log(sync_log, str(exc), two_fa_status="timed_out")
                        elif isinstance(exc, ProviderError):
                            _fail_sync_log(sync_log, str(exc))
                        else:
                            log.error("Background sync failed for %s: %s", provider_name, exc)
                            _fail_sync_log(sync_log, str(exc))
                else:
                    # Timeout — abandon the task and fail the sync log
                    log.error("Sync timed out after %ds for %s", timeout, provider_name)
                    _fail_sync_log(sync_log, f"Sync timed out after {timeout}s")
                    sync_task.cancel()

                await db.commit()
        except Exception as e:
            # Session itself might be broken — try a fresh one for the error update
            log.error("Background sync session error for %s: %s", provider_name, e)
            try:
                async with async_session_maker() as err_db:
                    err_log = await err_db.get(SyncLog, sync_log_id)
                    if err_log and err_log.status in ("running", "awaiting_2fa"):
                        err_log.status = "failed"
                        err_log.error_message = f"Internal error: {e}"
                        err_log.completed_at = int(time.time())
                        await err_db.commit()
            except Exception:
                log.error("Failed to update SyncLog %d after error", sync_log_id)
        finally:
            remove_session(sync_log_id)


def _fail_sync_log(
    sync_log: SyncLog,
    error_message: str,
    two_fa_status: str | None = None,
) -> None:
    """Mark a SyncLog as failed with an error message."""
    sync_log.status = "failed"
    sync_log.error_message = error_message
    sync_log.completed_at = int(time.time())
    if two_fa_status:
        sync_log.two_fa_status = two_fa_status


def _build_2fa_handler(
    db: AsyncSession, sync_log: SyncLog, provider_name: str
) -> TwoFAHandler:
    """Build a 2FA handler closure for background sync."""

    async def handler(challenge: TwoFAChallenge) -> str:
        session = get_session(sync_log.id)
        if session:
            # Retry — reset event for next wait
            session.reset()
            session.challenge = challenge
        else:
            session = create_session(sync_log.id, provider_name, challenge)

        sync_log.status = "awaiting_2fa"
        sync_log.two_fa_status = "awaiting_code"
        sync_log.two_fa_method = challenge.method
        await db.commit()  # Make visible to polling endpoint

        try:
            code = await session.wait_for_code()
            sync_log.status = "running"
            sync_log.two_fa_status = "code_submitted"
            await db.commit()
            return code
        except TwoFATimeoutError:
            raise  # Let _background_sync handle the status update

    return handler


async def _check_rate_limit(db: AsyncSession, provider: FinanceProvider) -> None:
    """Check per-provider rate limit."""
    now = int(time.time())
    day_ago = now - _ONE_DAY
    sync_count = await db.scalar(
        select(func.count())
        .select_from(SyncLog)
        .where(
            SyncLog.provider == provider.provider_name,
            SyncLog.status == "success",
            SyncLog.completed_at >= day_ago,
        )
    )
    if sync_count and sync_count >= provider.max_syncs_per_day:
        raise RateLimitError(
            f"Daily limit reached — {provider.max_syncs_per_day} syncs in the last 24 hours.",
            provider.provider_name,
        )


async def _run_sync(
    db: AsyncSession,
    provider: FinanceProvider,
    sync_log: SyncLog,
    two_fa_handler: TwoFAHandler | None = None,
) -> SyncLog:
    """Execute sync for a single provider.

    sync_log must already exist in db (created by start_sync).
    """
    log.info("Sync started for %s", provider.provider_name)

    credential = await get_credential(db, provider.provider_name)
    if not credential:
        sync_log.status = "failed"
        sync_log.error_message = f"No credentials configured for {provider.display_name}"
        sync_log.completed_at = int(time.time())
        return sync_log

    # Decrypt credential data
    cred_data = json.loads(decrypt(credential.encrypted_data))

    # Decrypt session data if present
    session_data = None
    if credential.session_data:
        session_data = json.loads(decrypt(credential.session_data))

    # Run provider sync
    result: SyncResult = await provider.sync(
        credential_data=cred_data,
        cursor=credential.sync_cursor,
        session_data=session_data,
        two_fa_handler=two_fa_handler,
    )

    # Log provider errors (non-fatal)
    if result.errors:
        for err in result.errors:
            log.warning("%s error: %s", provider.provider_name, err)
        sync_log.error_message = "; ".join(result.errors)

    # Upsert accounts and transactions
    accounts_synced = set()
    transactions_added = 0

    for account in result.accounts:
        await _upsert_account(db, account, provider.provider_name)
        accounts_synced.add(account.id)

    for tx in result.transactions:
        await _upsert_transaction(db, tx)
        transactions_added += 1

    # Save session data if returned (browser providers)
    if result.session_data is not None:
        credential.session_data = encrypt(json.dumps(result.session_data))

    # Update cursor
    credential.sync_cursor = str(int(time.time()))
    await db.flush()

    # Auto-apply category memory to new uncategorized transactions
    if accounts_synced:
        uncat_result = await db.scalars(
            select(Transaction).where(
                Transaction.account_id.in_(list(accounts_synced)),
                Transaction.category == "Uncategorized",
            )
        )
        uncat_txns = list(uncat_result.all())
        if uncat_txns:
            matched, _ = await apply_memory_rules(db, uncat_txns)
            if matched:
                log.info(
                    "Auto-categorized %d transactions from memory for %s",
                    len(matched),
                    provider.provider_name,
                )

    sync_log.accounts_synced = len(accounts_synced)
    sync_log.transactions_added = transactions_added
    sync_log.status = "success"
    sync_log.completed_at = int(time.time())
    sync_log.raw_response = result.raw_json

    log.info(
        "Sync complete for %s: %d accounts, %d transactions",
        provider.provider_name,
        len(accounts_synced),
        transactions_added,
    )

    return sync_log


async def _upsert_account(
    db: AsyncSession, account: ProviderAccount, provider_name: str
) -> None:
    """Insert or update an account from provider data."""
    now = int(time.time())

    stmt = insert(Account).values(
        id=account.id,
        provider=provider_name,
        org_name=account.org_name,
        name=account.name,
        account_type=account.account_type,
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


async def _upsert_transaction(db: AsyncSession, tx: ProviderTransaction) -> None:
    """Insert or update a transaction from provider data.

    On conflict, core fields are updated but user-managed fields are preserved.
    """
    now = int(time.time())

    stmt = insert(Transaction).values(
        account_id=tx.account_id,
        external_id=tx.id,
        posted_at=tx.date,
        transacted_at=tx.transacted_at,
        amount=tx.amount,
        description=tx.description,
        is_pending=tx.pending,
        raw_data=json.dumps({
            "provider_id": tx.id,
            "pending": tx.pending,
            "extra": tx.extra,
        }),
        created_at=now,
    )

    stmt = stmt.on_conflict_do_update(
        index_elements=["account_id", "external_id"],
        set_={
            "posted_at": stmt.excluded.posted_at,
            "transacted_at": stmt.excluded.transacted_at,
            "amount": stmt.excluded.amount,
            "description": stmt.excluded.description,
            "is_pending": stmt.excluded.is_pending,
            "raw_data": stmt.excluded.raw_data,
            "updated_at": now,
        },
    )

    await db.execute(stmt)
