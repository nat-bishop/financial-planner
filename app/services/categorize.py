"""Batch transaction categorization using Gemini."""

import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.clients.gemini import GeminiClient
from app.core.config import settings
from app.models import Category, Transaction
from app.schemas import (
    BatchCategorizationResponse,
    CategorizeResponse,
    CategorizeResult,
)

log = logging.getLogger(__name__)

UNABLE_TO_CATEGORIZE = "Unable to Categorize"


def _build_system_prompt(categories: list[Category]) -> str:
    """Build the system prompt with available categories."""
    cat_lines = "\n".join(
        f"- {c.name}: {c.description}" if c.description else f"- {c.name}"
        for c in categories
    )
    return f"""You are a financial transaction categorizer. For each transaction, assign the
single most appropriate category from the list below. Use the descriptions to
determine which category fits best.

Always assign your best guess for a category, and use the confidence score to
indicate how certain you are. A confidence of 1.0 means you are completely
certain. A confidence below 0.5 means you are largely guessing.

Categories:
{cat_lines}

For each transaction return:
- category: exactly one category name from the list above
- subcategory: a more specific label within the category (e.g., "Groceries"
  within "Food & Dining", "Gas" within "Transportation"). Null if not applicable.
- confidence: 0.0 to 1.0
- reasoning: one sentence explaining your choice"""


def _build_transaction_prompt(transactions: list[Transaction]) -> str:
    """Build the user prompt with transaction data."""
    items = []
    for tx in transactions:
        account = tx.account
        date_str = time.strftime("%Y-%m-%d", time.gmtime(tx.posted_at))
        item = {
            "id": tx.id,
            "description": tx.description,
            "amount": tx.amount,
            "date": date_str,
            "is_pending": tx.is_pending,
            "account_name": account.name if account else "Unknown",
            "bank_name": account.org_name if account else None,
            "account_type": account.account_type if account else None,
        }
        items.append(str(item))
    return "Categorize these transactions:\n" + "\n".join(items)


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
        query = query.where(Transaction.category.is_(None))
        query = query.limit(settings.categorize_limit)

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

    system_prompt = _build_system_prompt(categories)
    threshold = settings.categorize_confidence_threshold
    batch_size = settings.categorize_batch_size

    all_results: list[CategorizeResult] = []
    categorized_count = 0
    unable_count = 0

    # Process in batches (sequential to respect rate limits)
    for i in range(0, len(transactions), batch_size):
        batch = transactions[i : i + batch_size]
        user_prompt = _build_transaction_prompt(batch)

        llm_response = await client.generate_structured(
            user_prompt,
            BatchCategorizationResponse,
            system=system_prompt,
            model=settings.gemini_categorize_model,
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
