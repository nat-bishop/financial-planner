"""Provider registry.

Access providers via get_provider() and list_providers().
"""

from __future__ import annotations

from app.providers.base import (
    AuthenticationError,
    FinanceProvider,
    ProviderError,
    RateLimitError,
)
from app.providers.models import ProviderAccount, ProviderTransaction, SyncResult

_PROVIDERS: dict[str, FinanceProvider] = {}


def _init_providers() -> None:
    """Lazily initialize provider registry."""
    if _PROVIDERS:
        return

    from app.providers.simplefin import SimpleFINProvider

    _PROVIDERS["simplefin"] = SimpleFINProvider()

    try:
        from app.providers.nelnet import NelnetProvider

        _PROVIDERS["nelnet"] = NelnetProvider()
    except ImportError:
        # Playwright not installed — skip browser providers
        pass


def get_provider(name: str) -> FinanceProvider:
    """Get a provider by name. Raises KeyError if not found."""
    _init_providers()
    if name not in _PROVIDERS:
        raise KeyError(f"Unknown provider: {name}")
    return _PROVIDERS[name]


def list_providers() -> list[FinanceProvider]:
    """Return all registered providers."""
    _init_providers()
    return list(_PROVIDERS.values())


__all__ = [
    "AuthenticationError",
    "FinanceProvider",
    "ProviderAccount",
    "ProviderError",
    "ProviderTransaction",
    "RateLimitError",
    "SyncResult",
    "get_provider",
    "list_providers",
]
