"""User settings CRUD endpoints."""

import json
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import UserSetting
from app.schemas import SettingResponse, SettingValue

router = APIRouter()

VALID_KEYS = {
    "projection_income_sources",
    "projection_monthly_contribution",
    "projection_return_rates",
}


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(
    key: str,
    db: AsyncSession = Depends(get_db),
) -> SettingResponse:
    """Get a user setting by key."""
    setting = await db.get(UserSetting, key)
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    return SettingResponse(key=setting.key, value=json.loads(setting.value))


@router.put("/{key}", response_model=SettingResponse)
async def put_setting(
    key: str,
    body: SettingValue,
    db: AsyncSession = Depends(get_db),
) -> SettingResponse:
    """Create or update a user setting."""
    if key not in VALID_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown setting key: {key}")

    setting = await db.get(UserSetting, key)
    if setting:
        setting.value = json.dumps(body.value)
        setting.updated_at = int(time.time())
    else:
        setting = UserSetting(
            key=key,
            value=json.dumps(body.value),
            updated_at=int(time.time()),
        )
        db.add(setting)
    return SettingResponse(key=key, value=body.value)


@router.delete("/{key}")
async def delete_setting(
    key: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a user setting."""
    setting = await db.get(UserSetting, key)
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    await db.delete(setting)
    await db.flush()
    return {"status": "deleted"}
