import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.encryption import encrypt
from app.models import Credential, SyncLog
from app.plaid import PlaidClient
from app.schemas import CredentialResponse, SyncResponse

router = APIRouter()


@router.post("/sandbox-token", response_model=CredentialResponse)
async def create_sandbox_token(
    institution_id: str = "ins_109508",  # First Platypus Bank
    db: AsyncSession = Depends(get_db),
) -> Credential:
    """Create credentials using Plaid sandbox (no Link UI needed).

    This endpoint bypasses the normal Link flow for testing.
    Only works in sandbox environment.

    Default institution is First Platypus Bank (ins_109508).
    Other sandbox institutions:
    - ins_109509: First Gingham Credit Union
    - ins_109510: Tattersall Federal Credit Union
    """
    if settings.plaid_environment != "sandbox":
        raise HTTPException(400, "Only available in sandbox environment")

    # Check if credentials already exist
    existing = await db.scalar(
        select(Credential).where(Credential.provider == "plaid")
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Plaid credentials already configured. Delete existing credentials first.",
        )

    client = PlaidClient()

    try:
        # Create sandbox public token directly (skips Link UI)
        public_token = await client.create_sandbox_public_token(
            institution_id=institution_id, products=["transactions"]
        )

        # Exchange for access token
        access_token, item_id = await client.exchange_public_token(public_token)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to create sandbox credentials: {e}",
        ) from None

    # Encrypt and store
    now = int(time.time())
    credential = Credential(
        id=str(uuid.uuid4()),
        provider="plaid",
        encrypted_data=encrypt(
            json.dumps({"access_token": access_token, "item_id": item_id})
        ),
        created_at=now,
    )
    db.add(credential)
    await db.flush()

    return credential


@router.post("/link-token")
async def create_link_token() -> dict:
    """Create a Plaid Link token for frontend use.

    Use this token with Plaid Link in your frontend to initiate
    the bank connection flow. After the user completes Link,
    exchange the public_token via POST /sync/credentials.
    """
    client = PlaidClient()

    try:
        link_token = await client.create_link_token(user_id="default")
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to create link token: {e}",
        ) from None

    return {"link_token": link_token}


@router.post("/credentials", response_model=CredentialResponse)
async def exchange_token(
    public_token: str,
    db: AsyncSession = Depends(get_db),
) -> Credential:
    """Exchange a Plaid public_token for access credentials.

    After a user completes the Plaid Link flow, call this endpoint
    with the public_token to store the access credentials.
    """
    # Check if credentials already exist
    existing = await db.scalar(
        select(Credential).where(Credential.provider == "plaid")
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Plaid credentials already configured. Delete existing credentials first.",
        )

    client = PlaidClient()

    try:
        access_token, item_id = await client.exchange_public_token(public_token)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to exchange token: {e}",
        ) from None

    # Encrypt and store
    now = int(time.time())
    credential = Credential(
        id=str(uuid.uuid4()),
        provider="plaid",
        encrypted_data=encrypt(
            json.dumps({"access_token": access_token, "item_id": item_id})
        ),
        created_at=now,
    )
    db.add(credential)
    await db.flush()

    return credential


@router.delete("/credentials")
async def delete_credentials(db: AsyncSession = Depends(get_db)) -> dict:
    """Delete stored Plaid credentials."""
    credential = await db.scalar(
        select(Credential).where(Credential.provider == "plaid")
    )
    if not credential:
        raise HTTPException(status_code=404, detail="No credentials found")

    await db.delete(credential)
    return {"status": "deleted"}


@router.post("/", response_model=SyncResponse)
async def trigger_sync(
    db: AsyncSession = Depends(get_db),
) -> SyncLog:
    """Trigger a sync from Plaid.

    Uses cursor-based sync for efficient incremental updates.
    On first sync, fetches all available transactions.
    On subsequent syncs, fetches only new/modified/removed transactions.

    Returns:
        SyncLog with results
    """
    from app.sync import sync_accounts

    try:
        sync_log = await sync_accounts(db)
        return sync_log
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
