"""Batch transaction categorization using Gemini with category memory."""

import logging
import time

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.clients.gemini import GeminiClient
from app.core.config import (
    CATEGORIZE_BATCH_SIZE,
    CATEGORIZE_CONFIDENCE_THRESHOLD,
    CATEGORIZE_LIMIT,
    GEMINI_CATEGORIZE_MODEL,
)
from app.models import (
    Account,
    Category,
    CategoryMemory,
    Transaction,
    normalize_description,
)
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
        items.append(
            {
                "id": tx.id,
                "description": tx.description,
                "amount": tx.amount,
                "date": time.strftime("%Y-%m-%d", time.gmtime(tx.posted_at)),
                "is_pending": tx.is_pending,
                "account_name": account.name if account else "Unknown",
                "bank_name": account.org_name if account else None,
                "account_type": account.account_type if account else None,
            }
        )
    return items


async def apply_memory_rules(
    db: AsyncSession,
    transactions: list[Transaction],
) -> tuple[list[Transaction], list[Transaction]]:
    """Apply category memory to transactions.

    Returns (matched, unmatched) — matched transactions are updated in-place.
    """
    if not transactions:
        return [], []

    # Build lookup: (normalized_pattern, account_id) -> memory entry
    patterns = {}
    for tx in transactions:
        key = (normalize_description(tx.description), tx.account_id)
        patterns[key] = patterns.get(key, [])
        patterns[key].append(tx)

    # Fetch all matching memory entries in one query
    pattern_values = list({k[0] for k in patterns})
    account_values = list({k[1] for k in patterns})

    result = await db.scalars(
        select(CategoryMemory).where(
            CategoryMemory.normalized_pattern.in_(pattern_values),
            CategoryMemory.account_id.in_(account_values),
        )
    )
    memory_entries = {(m.normalized_pattern, m.account_id): m for m in result.all()}

    matched = []
    unmatched = []
    now = int(time.time())

    for tx in transactions:
        key = (normalize_description(tx.description), tx.account_id)
        memory = memory_entries.get(key)
        if memory:
            tx.category = memory.category
            tx.categorize_confidence = None  # Memory match, not LLM
            tx.updated_at = now
            matched.append(tx)
        else:
            unmatched.append(tx)

    return matched, unmatched


async def cache_llm_results(
    db: AsyncSession,
    transactions: list[Transaction],
) -> None:
    """Cache LLM categorization results into category_memory.

    Uses INSERT ... ON CONFLICT DO NOTHING — user corrections are never overwritten.
    """
    now = int(time.time())
    for tx in transactions:
        if tx.category and tx.category not in ("Uncategorized", UNABLE_TO_CATEGORIZE):
            pattern = normalize_description(tx.description)
            stmt = insert(CategoryMemory).values(
                normalized_pattern=pattern,
                account_id=tx.account_id,
                category=tx.category,
                created_at=now,
            )
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["normalized_pattern", "account_id"],
            )
            await db.execute(stmt)


async def _fetch_memory_context(
    db: AsyncSession,
    account_ids: list[str],
) -> list[dict]:
    """Fetch category memory entries for prompt context (few-shot examples).

    Returns up to 50 most recently updated entries for the given accounts.
    """
    query = (
        select(CategoryMemory)
        .where(CategoryMemory.account_id.in_(account_ids))
        .order_by(
            CategoryMemory.updated_at.desc().nullslast(),
            CategoryMemory.created_at.desc(),
        )
        .limit(50)
    )
    result = await db.scalars(query)
    entries = result.all()

    # Fetch account names for display
    acct_result = await db.scalars(select(Account).where(Account.id.in_(account_ids)))
    acct_names = {a.id: a.name for a in acct_result.all()}

    return [
        {
            "pattern": e.normalized_pattern,
            "account_name": acct_names.get(e.account_id, "Unknown"),
            "category": e.category,
        }
        for e in entries
    ]


async def categorize_transactions(
    db: AsyncSession,
    client: GeminiClient,
    transaction_ids: list[int] | None = None,
) -> CategorizeResponse:
    """Categorize transactions using memory matching + Gemini fallback.

    1. Apply category memory (deterministic, free)
    2. Send unmatched to LLM in batches
    3. Cache LLM results into memory
    """
    # Fetch transactions
    query = select(Transaction).options(selectinload(Transaction.account))
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
            memory_matched=0,
            results=[],
        )

    # Step 1: Deterministic memory matching
    matched, unmatched = await apply_memory_rules(db, transactions)
    memory_matched_count = len(matched)

    # Record memory matches as results
    all_results: list[CategorizeResult] = [
        CategorizeResult(
            transaction_id=tx.id,
            description=tx.description,
            category=tx.category,
            suggested_category=tx.category,
            confidence=1.0,
            reasoning="Matched from category memory",
            applied=True,
        )
        for tx in matched
    ]

    # Step 2: LLM categorization for unmatched
    categorized_count = memory_matched_count
    unable_count = 0

    if unmatched:
        # Fetch categories for the prompt
        cat_result = await db.scalars(select(Category).order_by(Category.name))
        categories = list(cat_result.all())

        if not categories:
            return CategorizeResponse(
                total_processed=memory_matched_count,
                categorized=memory_matched_count,
                unable_to_categorize=0,
                memory_matched=memory_matched_count,
                results=all_results,
                error="No categories configured. Add categories before running categorization.",
            )

        # Fetch memory context for prompt enhancement
        account_ids = list({tx.account_id for tx in unmatched})
        memory_context = await _fetch_memory_context(db, account_ids)

        threshold = CATEGORIZE_CONFIDENCE_THRESHOLD
        batch_size = CATEGORIZE_BATCH_SIZE

        llm_categorized: list[Transaction] = []

        # Process in batches (sequential to respect rate limits)
        for i in range(0, len(unmatched), batch_size):
            batch = unmatched[i : i + batch_size]
            tx_data = _prepare_transactions(batch)
            system_prompt, user_prompt = render_parts(
                "categorize.j2",
                categories=categories,
                transactions=tx_data,
                memory_entries=memory_context,
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
                    tx.categorize_confidence = item.confidence
                    categorized_count += 1
                    llm_categorized.append(tx)
                else:
                    tx.category = UNABLE_TO_CATEGORIZE
                    tx.categorize_confidence = item.confidence
                    unable_count += 1

                tx.updated_at = int(time.time())

                all_results.append(
                    CategorizeResult(
                        transaction_id=tx.id,
                        description=tx.description,
                        category=tx.category,
                        suggested_category=item.category,
                        confidence=item.confidence,
                        reasoning=item.reasoning,
                        applied=applied,
                    )
                )

        # Step 3: Cache LLM results into memory
        await cache_llm_results(db, llm_categorized)

    return CategorizeResponse(
        total_processed=len(all_results),
        categorized=categorized_count,
        unable_to_categorize=unable_count,
        memory_matched=memory_matched_count,
        results=all_results,
    )
