import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.encryption import encrypt
from app.models import Credential, SyncLog
from app.schemas import CredentialCreate, CredentialResponse, SyncResponse
from app.simplefin import SimpleFINClient
from app.sync import sync_accounts

router = APIRouter()


@router.post("/credentials", response_model=CredentialResponse)
async def setup_credentials(
    data: CredentialCreate,
    db: AsyncSession = Depends(get_db),
) -> Credential:
    """Exchange a SimpleFIN setup token for access credentials.

    The setup token is obtained from SimpleFIN and can only be used once.
    The resulting access URL is encrypted and stored for future syncs.
    """
    # Check if credentials already exist
    existing = await db.scalar(
        select(Credential).where(Credential.provider == "simplefin")
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="SimpleFIN credentials already configured. Delete existing credentials first.",
        )

    try:
        # Claim the access URL from SimpleFIN
        access_url = await SimpleFINClient.claim_token(data.setup_token)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to claim SimpleFIN token: {e}",
        )

    # Encrypt and store
    now = int(time.time())
    credential = Credential(
        id=str(uuid.uuid4()),
        provider="simplefin",
        encrypted_data=encrypt(json.dumps({"access_url": access_url})),
        created_at=now,
    )
    db.add(credential)
    await db.flush()

    return credential


@router.delete("/credentials")
async def delete_credentials(db: AsyncSession = Depends(get_db)) -> dict:
    """Delete stored SimpleFIN credentials."""
    credential = await db.scalar(
        select(Credential).where(Credential.provider == "simplefin")
    )
    if not credential:
        raise HTTPException(status_code=404, detail="No credentials found")

    await db.delete(credential)
    return {"status": "deleted"}


@router.post("/", response_model=SyncResponse)
async def trigger_sync(
    start_date: int | None = None,
    end_date: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> SyncLog:
    """Trigger a sync from SimpleFIN.

    Args:
        start_date: Optional Unix timestamp for transaction start date (default: 60 days ago)
        end_date: Optional Unix timestamp for transaction end date (default: now)

    Returns:
        SyncLog with results
    """
    try:
        sync_log = await sync_accounts(db, start_date=start_date, end_date=end_date)
        return sync_log
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=list[SyncResponse])
async def get_sync_history(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
) -> list[SyncLog]:
    """Get sync operation history."""
    result = await db.scalars(
        select(SyncLog).order_by(SyncLog.started_at.desc()).limit(limit)
    )
    return list(result.all())
