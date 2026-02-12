"""SimpleFIN provider — thin adapter wrapping SimpleFINClient."""

from __future__ import annotations

import time
from typing import Any

from app.clients.simplefin import SimpleFINClient
from app.providers.base import (
    AuthenticationError,
    FinanceProvider,
    ProviderError,
    TwoFAHandler,
)
from app.providers.models import ProviderAccount, ProviderTransaction, SyncResult


class SimpleFINProvider(FinanceProvider):
    provider_name = "simplefin"
    display_name = "SimpleFIN Bridge"
    max_syncs_per_day = 24

    async def validate_credentials(self, raw_input: dict[str, Any]) -> dict[str, Any]:
        setup_token = raw_input.get("setup_token", "")
        if not setup_token:
            raise ProviderError("Missing setup_token", self.provider_name)
        try:
            access_url = await SimpleFINClient.claim_setup_token(setup_token)
        except Exception as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status == 403:
                raise AuthenticationError(
                    "Setup token already claimed. Get a new one from bridge.simplefin.org.",
                    self.provider_name,
                ) from None
            raise ProviderError(
                f"Failed to claim setup token: {e}",
                self.provider_name,
            ) from None
        return {"access_url": access_url}

    async def sync(
        self,
        credential_data: dict[str, Any],
        cursor: str | None,
        session_data: dict[str, Any] | None = None,
        two_fa_handler: TwoFAHandler | None = None,
    ) -> SyncResult:
        access_url = credential_data["access_url"]
        client = SimpleFINClient(access_url)

        now = int(time.time())
        start_date = int(cursor) if cursor else None

        response = await client.fetch_accounts(start_date=start_date, end_date=now)

        accounts = [
            ProviderAccount(
                id=a.id,
                name=a.name,
                currency=a.currency,
                balance_current=a.balance_current,
                balance_available=a.balance_available,
                balance_date=a.balance_date,
                org_name=a.org_name,
            )
            for a in response.accounts
        ]

        transactions = [
            ProviderTransaction(
                id=t.id,
                account_id=t.account_id,
                amount=t.amount,
                date=t.date,
                description=t.description,
                pending=t.pending,
                transacted_at=t.transacted_at,
                extra=t.extra,
            )
            for t in response.transactions
        ]

        return SyncResult(
            accounts=accounts,
            transactions=transactions,
            errors=response.errors,
            raw_json=response.raw_json,
        )
