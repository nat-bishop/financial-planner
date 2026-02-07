"""SimpleFIN Bridge API client.

SimpleFIN Bridge provides bank data via a simple REST API:
- Setup token → claim → access URL (one-time)
- GET {access_url}/accounts with date-range filtering
- Amounts as string decimals, negative = expense (matches our convention)
- Rate limit: ~24 requests/day, 60-day max date range
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlparse

import httpx


@dataclass
class SFAccount:
    """Account data from SimpleFIN."""

    id: str
    name: str
    currency: str
    balance_current: int  # cents
    balance_available: int | None  # cents
    balance_date: int | None  # Unix timestamp
    org_name: str | None


@dataclass
class SFTransaction:
    """Transaction data from SimpleFIN."""

    id: str
    account_id: str
    amount: int  # cents (negative = expense, positive = income)
    date: int  # Unix timestamp
    description: str
    pending: bool


@dataclass
class SFSyncResponse:
    """Response from SimpleFIN accounts endpoint."""

    accounts: list[SFAccount]
    transactions: list[SFTransaction]
    errors: list[str]
    raw_json: str


def _sfin_amount_to_cents(amount_str: str) -> int:
    """Convert SimpleFIN string decimal amount to cents.

    Uses Decimal for precision (float would lose cents on values like "10.15").
    No sign inversion — SimpleFIN matches our convention.
    """
    d = Decimal(amount_str)
    return int((d * 100).to_integral_value(rounding=ROUND_HALF_UP))


_SIXTY_DAYS = 60 * 86400


class SimpleFINClient:
    """Async client for SimpleFIN Bridge API."""

    @classmethod
    async def claim_setup_token(cls, setup_token: str) -> str:
        """Claim a one-time setup token and return the access URL.

        Args:
            setup_token: Base64-encoded claim URL from SimpleFIN Bridge.

        Returns:
            Access URL with embedded Basic Auth credentials.

        Raises:
            httpx.HTTPStatusError: 403 if token already claimed.
        """
        claim_url = base64.b64decode(setup_token).decode("utf-8")
        async with httpx.AsyncClient() as client:
            resp = await client.post(claim_url)
            resp.raise_for_status()
            return resp.text

    def __init__(self, access_url: str) -> None:
        parsed = urlparse(access_url)
        self._auth = httpx.BasicAuth(
            username=parsed.username or "",
            password=parsed.password or "",
        )
        # Rebuild URL without credentials
        self._base_url = parsed._replace(
            netloc=parsed.hostname or ""
        ).geturl()

    async def fetch_accounts(
        self,
        start_date: int | None = None,
        end_date: int | None = None,
    ) -> SFSyncResponse:
        """Fetch accounts and transactions from SimpleFIN.

        Args:
            start_date: Unix timestamp for start of date range.
            end_date: Unix timestamp for end of date range.

        Returns:
            SFSyncResponse with accounts, transactions, and any errors.
        """
        now = int(time.time())
        if end_date is None:
            end_date = now
        if start_date is None:
            start_date = end_date - _SIXTY_DAYS

        # Cap at 60-day window
        if end_date - start_date > _SIXTY_DAYS:
            start_date = end_date - _SIXTY_DAYS

        params: dict[str, str] = {
            "start-date": str(start_date),
            "end-date": str(end_date + 1),  # exclusive — add 1 to include current second
            "pending": "1",
        }

        async with httpx.AsyncClient(auth=self._auth) as client:
            resp = await client.get(
                f"{self._base_url}/accounts",
                params=params,
            )
            resp.raise_for_status()

        data = resp.json()

        # Strip credentials from raw JSON before storing
        raw_json = json.dumps({
            "accounts_count": len(data.get("accounts", [])),
            "errors": data.get("errors", []),
        })

        accounts: list[SFAccount] = []
        transactions: list[SFTransaction] = []

        for acc_data in data.get("accounts", []):
            org = acc_data.get("org", {})
            org_name = org.get("name") or org.get("domain")

            balance_date = acc_data.get("balance-date")

            account = SFAccount(
                id=acc_data["id"],
                name=acc_data.get("name", ""),
                currency=acc_data.get("currency", "USD"),
                balance_current=_sfin_amount_to_cents(str(acc_data.get("balance", "0"))),
                balance_available=(
                    _sfin_amount_to_cents(str(acc_data["available-balance"]))
                    if acc_data.get("available-balance") is not None
                    else None
                ),
                balance_date=balance_date,
                org_name=org_name,
            )
            accounts.append(account)

            # Flatten nested transactions
            for tx_data in acc_data.get("transactions", []):
                posted = tx_data.get("posted", 0)
                pending = posted == 0
                if pending:
                    posted = now  # Substitute current time for pending

                transaction = SFTransaction(
                    id=tx_data["id"],
                    account_id=acc_data["id"],
                    amount=_sfin_amount_to_cents(str(tx_data.get("amount", "0"))),
                    date=posted,
                    description=tx_data.get("description", ""),
                    pending=pending,
                )
                transactions.append(transaction)

        return SFSyncResponse(
            accounts=accounts,
            transactions=transactions,
            errors=data.get("errors", []),
            raw_json=raw_json,
        )
