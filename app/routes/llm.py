import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.gemini import GeminiClient, get_gemini_client
from app.core.config import GEMINI_CATEGORIZE_MODEL, settings
from app.core.database import get_db
from app.schemas import (
    CategorizeRequest,
    CategorizeResponse,
    LLMStatusResponse,
)
from app.services.categorize import categorize_transactions

log = logging.getLogger(__name__)

router = APIRouter()


def _get_client() -> GeminiClient:
    """Wrapper for Depends — raises HTTPException on missing key."""
    try:
        return get_gemini_client()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.get("/status", response_model=LLMStatusResponse)
async def llm_status() -> LLMStatusResponse:
    """Check if Gemini is configured."""
    return LLMStatusResponse(
        configured=bool(settings.gemini_api_key),
        model=GEMINI_CATEGORIZE_MODEL,
    )


@router.post("/categorize", response_model=CategorizeResponse)
async def categorize(
    data: CategorizeRequest | None = None,
    db: AsyncSession = Depends(get_db),
    client: GeminiClient = Depends(_get_client),
) -> CategorizeResponse:
    """Categorize transactions using Gemini.

    With no body or empty body: categorize all uncategorized transactions.
    With transaction_ids: categorize/re-categorize those specific transactions.
    """
    transaction_ids = data.transaction_ids if data else None

    try:
        return await categorize_transactions(db, client, transaction_ids)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from None


