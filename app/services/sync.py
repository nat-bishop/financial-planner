"""Provider-agnostic sync orchestration.

sync_all() syncs all connected providers concurrently.
sync_provider() syncs a single provider with per-provider locking and rate limits.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt, encrypt
from app.models import Account, Credential, SyncLog, Transaction
from app.providers import (
    AuthenticationError,
    ProviderError,
    RateLimitError,
    get_provider,
)
from app.providers.base import FinanceProvider
from app.providers.models import ProviderAccount, ProviderTransaction, SyncResult

log = logging.getLogger(__name__)

_sync_locks: dict[str, asyncio.Lock] = {}
_ONE_DAY = 86400


def _get_lock(provider_name: str) -> asyncio.Lock:
    if provider_name not in _sync_locks:
        _sync_locks[provider_name] = asyncio.Lock()
    return _sync_locks[provider_name]


async def get_connected_providers(db: AsyncSession) -> list[str]:
    """Return names of providers that have stored credentials."""
    result = await db.scalars(select(Credential.provider))
    return list(result.all())


async def get_credential(db: AsyncSession, provider_name: str = "simplefin") -> Credential | None:
    """Get credential for a provider."""
    return await db.scalar(
        select(Credential).where(Credential.provider == provider_name)
    )


async def sync_all(db: AsyncSession) -> list[SyncLog]:
    """Sync all connected providers concurrently.

    Returns list of SyncLogs (one per provider). Exceptions become failed logs.
    """
    connected = await get_connected_providers(db)
    if not connected:
        return []

    results = await asyncio.gather(
        *[sync_provider(db, name) for name in connected],
        return_exceptions=True,
    )

    sync_logs: list[SyncLog] = []
    for i, result in enumerate(results):
        if isinstance(result, SyncLog):
            sync_logs.append(result)
        elif isinstance(result, BaseException):
            # Create a failed SyncLog for the exception
            now = int(time.time())
            provider_name = connected[i]
            error_msg = str(result)
            if isinstance(result, ProviderError):
                error_msg = f"[{result.provider}] {result}"
            failed_log = SyncLog(
                provider=provider_name,
                started_at=now,
                completed_at=now,
                status="failed",
                error_message=error_msg,
            )
            db.add(failed_log)
            sync_logs.append(failed_log)
    await db.flush()
    return sync_logs


async def sync_provider(db: AsyncSession, provider_name: str) -> SyncLog:
    """Sync a single provider with locking, rate limiting, and timeout.

    Raises:
        ProviderError: On provider failure.
        RateLimitError: If daily limit reached.
        RuntimeError: If sync already in progress for this provider.
    """
    provider = get_provider(provider_name)
    lock = _get_lock(provider_name)

    if lock.locked():
        raise RuntimeError(f"Sync already in progress for {provider_name}")

    # Rate limit: per-provider
    await _check_rate_limit(db, provider)

    async with lock:
        # Timeout: 30s for API providers, 180s for browser providers
        from app.providers.browser import BrowserProvider

        timeout = 180 if isinstance(provider, BrowserProvider) else 30
        try:
            return await asyncio.wait_for(
                _run_sync(db, provider), timeout=timeout
            )
        except TimeoutError:
            raise ProviderError(
                "Sync timed out",
                provider_name,
                detail={"timeout_seconds": timeout},
            ) from None


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


async def _run_sync(db: AsyncSession, provider: FinanceProvider) -> SyncLog:
    """Execute sync for a single provider."""
    now = int(time.time())

    # Create SyncLog entry
    sync_log = SyncLog(
        provider=provider.provider_name,
        started_at=now,
        status="running",
    )
    db.add(sync_log)
    await db.flush()

    log.info("Sync started for %s", provider.provider_name)

    try:
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

    except (ProviderError, AuthenticationError, RateLimitError):
        raise
    except Exception as e:
        log.error("Sync failed for %s: %s", provider.provider_name, e)
        sync_log.status = "failed"
        sync_log.error_message = str(e)
        sync_log.completed_at = int(time.time())
        await db.commit()
        raise

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
