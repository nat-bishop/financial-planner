"""Sync routes — background sync tasks with 2FA relay."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import SyncLog
from app.providers import (
    RateLimitError,
    get_provider,
    list_providers,
)
from app.schemas import (
    ProviderSyncStatus,
    SyncResponse,
    SyncStatusResponse,
    SyncTriggerResponse,
    TwoFACodeSubmission,
    TwoFAStatusResponse,
    TwoFASubmitResponse,
)
from app.services.sync import get_connected_providers, start_sync, start_sync_all
from app.services.two_fa import TWO_FA_MAX_ATTEMPTS, get_session

log = logging.getLogger(__name__)

router = APIRouter()


@router.post("/", response_model=SyncTriggerResponse, status_code=202)
async def trigger_sync_all(
    db: AsyncSession = Depends(get_db),
) -> SyncTriggerResponse:
    """Sync all connected providers.

    Returns 202 immediately with SyncLog IDs. Poll GET /sync/status for progress.
    """
    connected = await get_connected_providers(db)
    if not connected:
        raise HTTPException(status_code=400, detail="No providers connected")

    sync_logs = await start_sync_all(db)
    return SyncTriggerResponse(
        sync_ids=[s.id for s in sync_logs],
        message=f"Sync started for {len(sync_logs)} provider(s)",
    )


@router.post("/{provider_name}", response_model=SyncTriggerResponse, status_code=202)
async def trigger_sync_one(
    provider_name: str,
    db: AsyncSession = Depends(get_db),
) -> SyncTriggerResponse:
    """Sync a single provider.

    Returns 202 immediately with SyncLog ID. Poll GET /sync/status for progress.
    """
    try:
        get_provider(provider_name)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Unknown provider: {provider_name}"
        ) from None

    try:
        sync_log = await start_sync(provider_name, db)
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e)) from None
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None

    return SyncTriggerResponse(
        sync_ids=[sync_log.id],
        message=f"Sync started for {provider_name}",
    )


@router.post("/{sync_log_id:int}/2fa", response_model=TwoFASubmitResponse)
async def submit_2fa_code(
    sync_log_id: int,
    body: TwoFACodeSubmission,
) -> TwoFASubmitResponse:
    """Submit a 2FA verification code for an active sync."""
    session = get_session(sync_log_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="No active 2FA session for this sync",
        )

    if session.max_attempts_exceeded:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum attempts ({TWO_FA_MAX_ATTEMPTS}) exceeded",
        )

    session.submit_code(body.code)
    return TwoFASubmitResponse(
        status="submitted",
        attempts=session.attempts,
    )


@router.get("/{sync_log_id:int}/2fa", response_model=TwoFAStatusResponse)
async def get_2fa_status(sync_log_id: int) -> TwoFAStatusResponse:
    """Get 2FA challenge details for an active sync."""
    session = get_session(sync_log_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="No active 2FA session for this sync",
        )

    return TwoFAStatusResponse(
        sync_log_id=session.sync_log_id,
        status="awaiting_code" if not session.max_attempts_exceeded else "max_attempts",
        method=session.challenge.method,
        prompt=session.challenge.prompt,
        methods_available=session.challenge.methods_available,
        attempts=session.attempts,
        max_attempts=TWO_FA_MAX_ATTEMPTS,
    )


@router.get("/status", response_model=SyncStatusResponse)
async def sync_status(
    db: AsyncSession = Depends(get_db),
) -> SyncStatusResponse:
    """Get per-provider sync status for polling."""
    providers = list_providers()
    statuses: list[ProviderSyncStatus] = []
    any_running = False

    for p in providers:
        last_sync = await db.scalar(
            select(SyncLog)
            .where(SyncLog.provider == p.provider_name)
            .order_by(SyncLog.started_at.desc())
            .limit(1)
        )

        if not last_sync:
            statuses.append(
                ProviderSyncStatus(
                    provider=p.provider_name,
                    display_name=p.display_name,
                    status="idle",
                )
            )
            continue

        status = ProviderSyncStatus(
            provider=p.provider_name,
            display_name=p.display_name,
            status=last_sync.status,
            started_at=last_sync.started_at,
            completed_at=last_sync.completed_at,
            error_message=last_sync.error_message,
        )

        if last_sync.status in ("running", "awaiting_2fa"):
            any_running = True
            if last_sync.status == "awaiting_2fa":
                session = get_session(last_sync.id)
                status.two_fa_sync_id = last_sync.id
                status.two_fa_method = last_sync.two_fa_method
                status.two_fa_prompt = session.challenge.prompt if session else None

        statuses.append(status)

    return SyncStatusResponse(providers=statuses, any_running=any_running)


@router.get("/logs", response_model=list[SyncResponse])
async def sync_logs(
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[SyncLog]:
    """Get recent sync history."""
    result = await db.scalars(
        select(SyncLog).order_by(SyncLog.started_at.desc()).limit(limit)
    )
    return list(result.all())
