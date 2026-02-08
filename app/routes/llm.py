import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.gemini import GeminiClient, get_gemini_client
from app.core.config import settings
from app.core.database import get_db
from app.models import Account, Transaction
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
        model=settings.gemini_categorize_model,
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
    accounts = await db.scalars(select(Account))
    account_list = list(accounts.all())

    now = int(time.time())
    thirty_days_ago = now - (30 * 86400)

    # Get recent spending summary
    spending_result = await db.execute(
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
    spending_rows = spending_result.all()

    # Build system prompt with financial context
    account_summary = "\n".join(
        f"- {a.name} ({a.org_name or 'Unknown'}): ${(a.balance_current or 0) / 100:.2f}"
        for a in account_list
    ) or "No accounts connected."

    spending_summary = "\n".join(
        f"- {row.category or 'Uncategorized'}: ${abs(row.total) / 100:.2f} ({row.count} transactions)"
        for row in spending_rows
    ) or "No spending data."

    system = f"""You are a helpful personal finance assistant. Answer questions about the user's finances.
Be concise and practical. Use the financial context below to inform your answers.

Account Summary:
{account_summary}

Last 30 Days Spending:
{spending_summary}"""

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
