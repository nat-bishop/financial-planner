"""Provider credential management routes."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.encryption import encrypt
from app.models import Credential, SyncLog
from app.providers import (
    AuthenticationError,
    ProviderError,
    get_provider,
    list_providers,
)
from app.schemas import (
    CredentialResponse,
    NelnetCredentialInput,
    ProviderStatusResponse,
    SimpleFINCredentialInput,
)

router = APIRouter()

CREDENTIAL_SCHEMAS: dict[str, type] = {
    "simplefin": SimpleFINCredentialInput,
    "nelnet": NelnetCredentialInput,
}


async def get_provider_statuses(db: AsyncSession) -> list[ProviderStatusResponse]:
    """Build provider status list (shared by health and providers endpoints)."""
    statuses: list[ProviderStatusResponse] = []
    for p in list_providers():
        cred = await db.scalar(
            select(Credential).where(Credential.provider == p.provider_name)
        )
        last_sync = await db.scalar(
            select(SyncLog)
            .where(SyncLog.provider == p.provider_name)
            .order_by(SyncLog.started_at.desc())
            .limit(1)
        )
        statuses.append(
            ProviderStatusResponse(
                provider=p.provider_name,
                display_name=p.display_name,
                connected=cred is not None,
                last_sync_at=last_sync.started_at if last_sync else None,
                last_sync_status=last_sync.status if last_sync else None,
            )
        )
    return statuses


@router.get("/", response_model=list[ProviderStatusResponse])
async def list_provider_status(
    db: AsyncSession = Depends(get_db),
) -> list[ProviderStatusResponse]:
    """List all providers with connection status."""
    return await get_provider_statuses(db)


@router.post("/{name}/credentials", response_model=CredentialResponse)
async def store_credentials(
    name: str,
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> Credential:
    """Store credentials for a provider.

    Body depends on provider:
    - SimpleFIN: {"setup_token": "..."}
    - Nelnet: {"username": "...", "password": "..."}
    """
    try:
        provider = get_provider(name)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Unknown provider: {name}"
        ) from None

    # Check if credentials already exist
    existing = await db.scalar(select(Credential).where(Credential.provider == name))
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"{provider.display_name} credentials already configured. Delete existing credentials first.",
        )

    schema = CREDENTIAL_SCHEMAS.get(name)
    if schema:
        try:
            validated = schema(**body)
            body = validated.model_dump()
        except Exception as e:
            raise HTTPException(status_code=422, detail=str(e)) from None

    try:
        cred_data = await provider.validate_credentials(body)
    except AuthenticationError as e:
        raise HTTPException(status_code=401, detail=str(e)) from None
    except ProviderError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    now = int(time.time())
    credential = Credential(
        id=str(uuid.uuid4()),
        provider=name,
        encrypted_data=encrypt(json.dumps(cred_data)),
        created_at=now,
    )
    db.add(credential)
    await db.flush()

    return credential


@router.put("/{name}/credentials", response_model=CredentialResponse)
async def update_credentials(
    name: str,
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> Credential:
    """Update credentials for a provider."""
    try:
        provider = get_provider(name)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Unknown provider: {name}"
        ) from None

    existing = await db.scalar(select(Credential).where(Credential.provider == name))
    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"No credentials found for {provider.display_name}",
        )

    schema = CREDENTIAL_SCHEMAS.get(name)
    if schema:
        try:
            validated = schema(**body)
            body = validated.model_dump()
        except Exception as e:
            raise HTTPException(status_code=422, detail=str(e)) from None

    try:
        cred_data = await provider.validate_credentials(body)
    except AuthenticationError as e:
        raise HTTPException(status_code=401, detail=str(e)) from None
    except ProviderError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    existing.encrypted_data = encrypt(json.dumps(cred_data))
    existing.session_data = None  # Clear session on credential change
    existing.updated_at = int(time.time())
    await db.flush()

    return existing


@router.delete("/{name}/credentials")
async def delete_credentials(
    name: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete credentials and session data for a provider."""
    credential = await db.scalar(select(Credential).where(Credential.provider == name))
    if not credential:
        raise HTTPException(status_code=404, detail="No credentials found")

    await db.delete(credential)
    return {"status": "deleted"}
