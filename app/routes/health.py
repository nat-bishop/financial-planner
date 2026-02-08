from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Account, Credential, SyncLog
from app.schemas import HealthResponse, SyncError

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    """Get system health status including last sync info."""
    # Get last sync
    last_sync = await db.scalar(
        select(SyncLog).order_by(SyncLog.started_at.desc()).limit(1)
    )

    # Check if credentials exist
    has_creds = await db.scalar(
        select(Credential).where(Credential.provider == "simplefin")
    )

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

    return HealthResponse(
        status="ok",
        has_credentials=has_creds is not None,
        last_sync_at=last_sync.started_at if last_sync else None,
        last_sync_status=last_sync.status if last_sync else None,
        account_count=account_count or 0,
        recent_errors=recent_errors,
    )
