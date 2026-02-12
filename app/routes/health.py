from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Account, Credential, SyncLog
from app.routes.providers import get_provider_statuses
from app.schemas import HealthResponse, SyncError

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HealthResponse:
    """Get system health status including per-provider sync info."""
    # Get last sync (across all providers)
    last_sync = await db.scalar(
        select(SyncLog).order_by(SyncLog.started_at.desc()).limit(1)
    )

    # Check if any credentials exist
    has_creds = await db.scalar(select(Credential).limit(1))

    # Get account count
    account_count = await db.scalar(select(func.count(Account.id)))

    # Get recent errors
    recent_errors_result = await db.scalars(
        select(SyncLog)
        .where(SyncLog.status == "failed")
        .order_by(SyncLog.started_at.desc())
        .limit(3)
    )

    recent_errors = [
        SyncError(at=e.started_at, message=e.error_message)
        for e in recent_errors_result.all()
    ]

    # Per-provider status
    provider_statuses = await get_provider_statuses(db)

    # Check for security warnings
    warnings: list[str] = []
    hostname = request.url.hostname or ""
    if request.url.scheme == "http" and hostname not in ("localhost", "127.0.0.1"):
        warnings.append(
            "Running over HTTP on a non-localhost address. "
            "Use HTTPS for credential security."
        )

    return HealthResponse(
        status="ok",
        has_credentials=has_creds is not None,
        providers=provider_statuses,
        last_sync_at=last_sync.started_at if last_sync else None,
        last_sync_status=last_sync.status if last_sync else None,
        account_count=account_count or 0,
        recent_errors=recent_errors,
        warnings=warnings,
    )
