"""Provider abstraction layer.

All finance data providers implement FinanceProvider. Provider errors use
three exception types: ProviderError (base), AuthenticationError, RateLimitError.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.providers.models import SyncResult


class ProviderError(Exception):
    """Base error for all provider failures."""

    def __init__(
        self,
        message: str,
        provider: str,
        detail: dict | None = None,
    ) -> None:
        self.provider = provider
        self.detail = detail or {}
        super().__init__(message)


class AuthenticationError(ProviderError):
    """Credentials invalid or expired."""


class RateLimitError(ProviderError):
    """Too many requests to provider."""


class FinanceProvider(ABC):
    """Abstract base for finance data providers.

    Providers fetch accounts and transactions from external sources.
    They return data only — no DB access.
    """

    provider_name: str
    display_name: str
    max_syncs_per_day: int

    @abstractmethod
    async def validate_credentials(self, raw_input: dict) -> dict:
        """Transform user input into storable credential data.

        SimpleFIN: {setup_token} -> {access_url}
        Nelnet: {username, password} -> {username, password} (validated)

        Raises:
            AuthenticationError: If credentials are invalid.
            ProviderError: On other failures.
        """

    @abstractmethod
    async def sync(
        self,
        credential_data: dict,
        cursor: str | None,
        session_data: dict | None = None,
    ) -> SyncResult:
        """Fetch accounts and transactions from the provider.

        No DB access — returns data for the sync service to upsert.

        Args:
            credential_data: Decrypted credential dict.
            cursor: Last sync timestamp (or None for first sync).
            session_data: Browser session state (browser providers only).

        Returns:
            SyncResult with accounts, transactions, and optional session state.

        Raises:
            AuthenticationError: If session expired / creds invalid.
            RateLimitError: If provider rate limit hit.
            ProviderError: On other failures.
        """
