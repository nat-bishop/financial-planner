"""Provider-agnostic data models.

These dataclasses are the contract between providers and the sync service.
Providers produce them; the sync service upserts them into the DB.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderAccount:
    """Account data returned by a provider."""

    id: str
    name: str
    currency: str
    balance_current: int  # cents
    balance_available: int | None = None
    balance_date: int | None = None
    org_name: str | None = None
    account_type: str | None = None


@dataclass
class ProviderTransaction:
    """Transaction data returned by a provider."""

    id: str
    account_id: str
    amount: int  # cents, negative = expense
    date: int  # Unix timestamp (posted_at)
    description: str
    pending: bool
    transacted_at: int | None = None
    extra: dict[str, Any] | None = None


@dataclass
class SyncResult:
    """Result of a provider sync operation."""

    accounts: list[ProviderAccount]
    transactions: list[ProviderTransaction]
    errors: list[str] = field(default_factory=list)
    raw_json: str = ""
    session_data: dict[str, Any] | None = (
        None  # Browser providers return updated session
    )
