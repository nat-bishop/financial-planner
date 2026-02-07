import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.encryption import encrypt
from app.models import Credential, SyncLog
from app.schemas import CredentialCreate, CredentialResponse, SyncResponse
from app.simplefin import SimpleFINClient
from app.sync import sync_accounts

log = logging.getLogger(__name__)

router = APIRouter()


@router.post("/credentials", response_model=CredentialResponse)
async def claim_setup_token(
    data: CredentialCreate,
    db: AsyncSession = Depends(get_db),
) -> Credential:
    """Claim a SimpleFIN setup token and store the access credentials.

    Get a setup token from https://bridge.simplefin.org, then pass it here.
    Setup tokens are one-time use — a 403 means the token was already claimed.
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
        access_url = await SimpleFINClient.claim_setup_token(data.setup_token)
    except Exception as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status == 403:
            raise HTTPException(
                status_code=400,
                detail="Setup token already claimed. Get a new one from bridge.simplefin.org.",
            ) from None
        raise HTTPException(
            status_code=400,
            detail=f"Failed to claim setup token: {e}",
        ) from None

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
    db: AsyncSession = Depends(get_db),
) -> SyncLog:
    """Trigger a sync from SimpleFIN.

    Fetches accounts and transactions for the date range since last sync
    (or last 60 days on first sync).

    Returns 429 if synced too recently (~24 requests/day limit).
    """
    try:
        sync_log = await sync_accounts(db)
        return sync_log
    except RuntimeError as e:
        msg = str(e)
        if "Too soon" in msg:
            raise HTTPException(status_code=429, detail=msg) from None
        raise HTTPException(status_code=409, detail=msg) from None
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from None


@router.get("/history", response_model=list[SyncResponse])
async def get_sync_history(
    limit: int = Query(default=10, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[SyncLog]:
    """Get sync operation history."""
    result = await db.scalars(
        select(SyncLog).order_by(SyncLog.started_at.desc()).limit(limit)
    )
    return list(result.all())
