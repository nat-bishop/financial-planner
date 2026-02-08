import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.gemini import GeminiClient, get_gemini_client
from app.core.config import GEMINI_CATEGORIZE_MODEL, settings
from app.core.database import get_db
from app.models import Account, Transaction, exclude_disabled_accounts
from app.prompts import render
from app.schemas import (
    CategorizeRequest,
    CategorizeResponse,
    ChatRequest,
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


@router.post("/chat")
async def chat(
    data: ChatRequest,
    db: AsyncSession = Depends(get_db),
    client: GeminiClient = Depends(_get_client),
) -> StreamingResponse:
    """Stream a chat response with financial context."""
    # Build context from account summary
    accounts = await db.scalars(
        select(Account).where(Account.is_disabled == False)  # noqa: E712
    )
    account_list = list(accounts.all())

    now = int(time.time())
    thirty_days_ago = now - (30 * 86400)

    # Get recent spending summary
    spending_query = (
        select(
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .where(Transaction.posted_at >= thirty_days_ago)
        .where(Transaction.amount < 0)
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount))
    )
    spending_result = await db.execute(exclude_disabled_accounts(spending_query))
    spending_rows = spending_result.all()

    # Build system prompt with financial context
    account_data = [
        {
            "name": a.name,
            "org_name": a.org_name or "Unknown",
            "balance": a.balance_current or 0,
        }
        for a in account_list
    ]
    spending_data = [
        {
            "category": row.category or "Uncategorized",
            "total": abs(row.total),
            "count": row.count,
        }
        for row in spending_rows
    ]
    system = render("chat.j2", accounts=account_data, spending=spending_data)

    async def event_stream():
        try:
            async for chunk in client.stream(data.message, system=system):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            log.error("Chat stream error: %s", e)
            yield f"data: Error: {e}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
