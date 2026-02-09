"""Sync routes — async sync with background tasks and polling."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import SyncLog
from app.providers import (
    AuthenticationError,
    ProviderError,
    RateLimitError,
    get_provider,
    list_providers,
)
from app.schemas import (
    ProviderSyncStatus,
    SyncResponse,
    SyncStatusResponse,
    SyncTriggerResponse,
)
from app.services.sync import get_connected_providers, sync_all, sync_provider

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

    sync_logs = await sync_all(db)
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
        sync_log = await sync_provider(db, provider_name)
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e)) from None
    except AuthenticationError as e:
        raise HTTPException(status_code=401, detail=str(e)) from None
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None

    return SyncTriggerResponse(
        sync_ids=[sync_log.id],
        message=f"Sync started for {provider_name}",
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

        if last_sync and last_sync.status == "running":
            any_running = True
            statuses.append(ProviderSyncStatus(
                provider=p.provider_name,
                display_name=p.display_name,
                status="running",
                started_at=last_sync.started_at,
            ))
        elif last_sync:
            statuses.append(ProviderSyncStatus(
                provider=p.provider_name,
                display_name=p.display_name,
                status=last_sync.status,
                started_at=last_sync.started_at,
                completed_at=last_sync.completed_at,
                error_message=last_sync.error_message,
            ))
        else:
            statuses.append(ProviderSyncStatus(
                provider=p.provider_name,
                display_name=p.display_name,
                status="idle",
            ))

    return SyncStatusResponse(providers=statuses, any_running=any_running)


@router.get("/logs", response_model=list[SyncResponse])
async def sync_logs(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> list[SyncLog]:
    """Get recent sync history."""
    result = await db.scalars(
        select(SyncLog)
        .order_by(SyncLog.started_at.desc())
        .limit(limit)
    )
    return list(result.all())
