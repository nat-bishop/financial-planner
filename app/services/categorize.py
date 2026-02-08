"""Batch transaction categorization using Gemini."""

import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.clients.gemini import GeminiClient
from app.core.config import (
    CATEGORIZE_BATCH_SIZE,
    CATEGORIZE_CONFIDENCE_THRESHOLD,
    CATEGORIZE_LIMIT,
    GEMINI_CATEGORIZE_MODEL,
)
from app.models import Category, Transaction
from app.prompts import render_parts
from app.schemas import (
    BatchCategorizationResponse,
    CategorizeResponse,
    CategorizeResult,
)

log = logging.getLogger(__name__)

UNABLE_TO_CATEGORIZE = "Unable to Categorize"


def _prepare_transactions(transactions: list[Transaction]) -> list[dict]:
    """Convert Transaction ORM objects to dicts for the prompt template."""
    items = []
    for tx in transactions:
        account = tx.account
        items.append({
            "id": tx.id,
            "description": tx.description,
            "amount": tx.amount,
            "date": time.strftime("%Y-%m-%d", time.gmtime(tx.posted_at)),
            "is_pending": tx.is_pending,
            "account_name": account.name if account else "Unknown",
            "bank_name": account.org_name if account else None,
            "account_type": account.account_type if account else None,
        })
    return items


async def categorize_transactions(
    db: AsyncSession,
    client: GeminiClient,
    transaction_ids: list[int] | None = None,
) -> CategorizeResponse:
    """Categorize transactions using Gemini.

    Args:
        db: Database session
        client: GeminiClient instance
        transaction_ids: Specific IDs to categorize, or None for uncategorized
    """
    # Fetch transactions
    query = (
        select(Transaction)
        .options(selectinload(Transaction.account))
    )
    if transaction_ids:
        query = query.where(Transaction.id.in_(transaction_ids))
    else:
        query = query.where(Transaction.category == "Uncategorized")
        query = query.limit(CATEGORIZE_LIMIT)

    result = await db.scalars(query)
    transactions = list(result.all())

    if not transactions:
        return CategorizeResponse(
            total_processed=0,
            categorized=0,
            unable_to_categorize=0,
            results=[],
        )

    # Fetch categories for the prompt
    cat_result = await db.scalars(select(Category).order_by(Category.name))
    categories = list(cat_result.all())

    if not categories:
        return CategorizeResponse(
            total_processed=0,
            categorized=0,
            unable_to_categorize=0,
            results=[],
            error="No categories configured. Add categories before running categorization.",
        )

    threshold = CATEGORIZE_CONFIDENCE_THRESHOLD
    batch_size = CATEGORIZE_BATCH_SIZE

    all_results: list[CategorizeResult] = []
    categorized_count = 0
    unable_count = 0

    # Process in batches (sequential to respect rate limits)
    for i in range(0, len(transactions), batch_size):
        batch = transactions[i : i + batch_size]
        tx_data = _prepare_transactions(batch)
        system_prompt, user_prompt = render_parts(
            "categorize.j2", categories=categories, transactions=tx_data,
        )

        llm_response = await client.generate_structured(
            user_prompt,
            BatchCategorizationResponse,
            system=system_prompt,
            model=GEMINI_CATEGORIZE_MODEL,
        )

        # Build lookup for matching
        tx_map = {tx.id: tx for tx in batch}

        for item in llm_response.transactions:
            tx = tx_map.get(item.id)
            if not tx:
                log.warning("LLM returned unknown transaction ID %d", item.id)
                continue

            applied = item.confidence >= threshold
            if applied:
                tx.category = item.category
                tx.subcategory = item.subcategory
                tx.categorize_confidence = item.confidence
                categorized_count += 1
            else:
                tx.category = UNABLE_TO_CATEGORIZE
                tx.subcategory = None
                tx.categorize_confidence = item.confidence
                unable_count += 1

            tx.updated_at = int(time.time())

            all_results.append(
                CategorizeResult(
                    transaction_id=tx.id,
                    description=tx.description,
                    category=tx.category,
                    suggested_category=item.category,
                    subcategory=item.subcategory,
                    confidence=item.confidence,
                    reasoning=item.reasoning,
                    applied=applied,
                )
            )

    return CategorizeResponse(
        total_processed=len(all_results),
        categorized=categorized_count,
        unable_to_categorize=unable_count,
        results=all_results,
    )
