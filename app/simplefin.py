"""SimpleFIN API client.

SimpleFIN provides:
- Stable transaction IDs (unique per account)
- Daily updates (24 requests/day limit)
- 60-day query windows
- Pre-normalized amounts
- Single-token auth (access URL)
"""

import base64
from dataclasses import dataclass

import httpx


@dataclass
class SimpleFINAccount:
    id: str
    org_domain: str
    org_name: str | None
    name: str
    currency: str
    balance: int  # cents
    available_balance: int | None  # cents
    balance_date: int  # unix timestamp
    transactions: list[dict]


@dataclass
class SimpleFINResponse:
    accounts: list[SimpleFINAccount]
    raw_json: str


class SimpleFINClient:
    def __init__(self, access_url: str):
        """Initialize with the access URL (contains embedded credentials)."""
        self.access_url = access_url

    @classmethod
    async def claim_token(cls, setup_token: str) -> str:
        """Exchange a setup token for an access URL.

        The setup token is a one-time use URL that returns the access URL.
        The access URL should be stored securely and used for all future requests.
        """
        # Decode the base64 setup token to get the claim URL
        claim_url = base64.b64decode(setup_token).decode("utf-8")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(claim_url)
            response.raise_for_status()
            # The response body is the access URL
            return response.text.strip()

    async def fetch_accounts(
        self, start_date: int | None = None, end_date: int | None = None
    ) -> SimpleFINResponse:
        """Fetch accounts and transactions from SimpleFIN.

        Args:
            start_date: Unix timestamp for transaction start date (optional)
            end_date: Unix timestamp for transaction end date (optional)

        Returns:
            SimpleFINResponse with accounts and raw JSON
        """
        # Build the accounts URL from access URL
        accounts_url = f"{self.access_url}/accounts"

        params = {}
        if start_date is not None:
            params["start-date"] = str(start_date)
        if end_date is not None:
            params["end-date"] = str(end_date)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(accounts_url, params=params)
            response.raise_for_status()

            raw_json = response.text
            data = response.json()

        accounts = []
        for org in data.get("accounts", []):
            org_domain = org.get("org", {}).get("domain", "unknown")
            org_name = org.get("org", {}).get("name")

            # SimpleFIN returns amounts as strings that need conversion to cents
            balance = _to_cents(org.get("balance"))
            available = _to_cents(org.get("available-balance"))

            account = SimpleFINAccount(
                id=org.get("id"),
                org_domain=org_domain,
                org_name=org_name,
                name=org.get("name", "Unknown Account"),
                currency=org.get("currency", "USD"),
                balance=balance,
                available_balance=available,
                balance_date=org.get("balance-date", 0),
                transactions=org.get("transactions", []),
            )
            accounts.append(account)

        return SimpleFINResponse(accounts=accounts, raw_json=raw_json)


def _to_cents(value: str | float | None) -> int | None:
    """Convert a decimal amount to cents."""
    if value is None:
        return None
    if isinstance(value, str):
        value = float(value)
    return int(round(value * 100))
