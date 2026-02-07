"""Plaid API client.

Plaid provides:
- Cursor-based transaction sync (efficient incremental updates)
- Rich transaction categories (personal_finance_category)
- Account type/subtype information
- Sandbox environment for testing

Note: The plaid-python SDK is synchronous, so we wrap calls with asyncio.to_thread()
to avoid blocking the FastAPI event loop.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime

import plaid
from plaid.api import plaid_api
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import (
    ItemPublicTokenExchangeRequest,
)
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.sandbox_public_token_create_request import (
    SandboxPublicTokenCreateRequest,
)
from plaid.model.transactions_sync_request import TransactionsSyncRequest

from app.config import settings


@dataclass
class PlaidAccount:
    """Account data from Plaid."""

    id: str
    name: str
    official_name: str | None
    type: str  # depository, credit, loan, investment
    subtype: str | None  # checking, savings, credit card, etc.
    mask: str | None  # last 4 digits
    balance_current: int  # cents
    balance_available: int | None  # cents
    currency: str


@dataclass
class PlaidTransaction:
    """Transaction data from Plaid."""

    id: str
    account_id: str
    amount: int  # cents (CONVERTED: positive in Plaid = expense → negative here)
    date: int  # Unix timestamp (CONVERTED from YYYY-MM-DD)
    description: str  # merchant_name or name
    pending: bool
    category: str | None  # from personal_finance_category


@dataclass
class PlaidSyncResponse:
    """Response from Plaid transactions/sync endpoint."""

    accounts: list[PlaidAccount]
    added: list[PlaidTransaction]
    modified: list[PlaidTransaction]
    removed: list[str]  # transaction_ids
    next_cursor: str
    has_more: bool
    raw_json: str


def _get_plaid_host() -> plaid.Environment:
    """Get Plaid host based on environment setting."""
    # Note: plaid-python SDK only has Sandbox and Production environments
    # "development" maps to Production with development credentials
    env_map = {
        "sandbox": plaid.Environment.Sandbox,
        "production": plaid.Environment.Production,
    }
    return env_map.get(settings.plaid_environment.lower(), plaid.Environment.Sandbox)


def _get_plaid_client() -> plaid_api.PlaidApi:
    """Create Plaid API client with current settings."""
    configuration = plaid.Configuration(
        host=_get_plaid_host(),
        api_key={
            "clientId": settings.plaid_client_id,
            "secret": settings.plaid_secret,
        },
    )
    return plaid_api.PlaidApi(plaid.ApiClient(configuration))


def _to_cents(amount: float | None) -> int:
    """Convert dollar amount to cents."""
    if amount is None:
        return 0
    return round(amount * 100)


def _plaid_amount_to_cents(amount: float) -> int:
    """Convert Plaid amount to our convention.

    Plaid: positive = money out (expense), negative = money in (income)
    Our convention: negative = expense, positive = income
    """
    return -round(amount * 100)


def _plaid_date_to_timestamp(date_str: str) -> int:
    """Convert Plaid date string to Unix timestamp.

    Plaid uses "YYYY-MM-DD" format.
    """
    return int(datetime.strptime(date_str, "%Y-%m-%d").timestamp())


def _parse_account(account_data) -> PlaidAccount:
    """Parse a Plaid account object to our dataclass."""
    balances = account_data.balances
    return PlaidAccount(
        id=account_data.account_id,
        name=account_data.name,
        official_name=getattr(account_data, "official_name", None),
        type=account_data.type,
        subtype=str(account_data.subtype) if account_data.subtype else None,
        mask=getattr(account_data, "mask", None),
        balance_current=_to_cents(balances.current),
        balance_available=_to_cents(balances.available) if balances.available else None,
        currency=balances.iso_currency_code or "USD",
    )


def _parse_transaction(tx_data) -> PlaidTransaction:
    """Parse a Plaid transaction object to our dataclass."""
    # Use merchant_name if available, otherwise fall back to name
    description = getattr(tx_data, "merchant_name", None) or tx_data.name or ""

    # Extract category from personal_finance_category if available
    category = None
    if hasattr(tx_data, "personal_finance_category") and tx_data.personal_finance_category:
        pfc = tx_data.personal_finance_category
        category = getattr(pfc, "primary", None)

    return PlaidTransaction(
        id=tx_data.transaction_id,
        account_id=tx_data.account_id,
        amount=_plaid_amount_to_cents(tx_data.amount),
        date=_plaid_date_to_timestamp(tx_data.date),
        description=description,
        pending=tx_data.pending,
        category=category,
    )


class PlaidClient:
    """Async wrapper around the sync plaid-python SDK."""

    def __init__(self):
        self._client = _get_plaid_client()

    async def create_sandbox_public_token(
        self, institution_id: str, products: list[str]
    ) -> str:
        """Create a public token in sandbox mode (bypasses Link UI).

        Only works in sandbox environment.
        """
        request = SandboxPublicTokenCreateRequest(
            institution_id=institution_id,
            initial_products=[Products(p) for p in products],
        )
        response = await asyncio.to_thread(
            self._client.sandbox_public_token_create, request
        )
        return response.public_token

    async def create_link_token(self, user_id: str) -> str:
        """Create a Link token for frontend Plaid Link flow."""
        request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id=user_id),
            client_name="Finance Planner",
            products=[Products("transactions")],
            country_codes=[CountryCode("US")],
            language="en",
        )
        response = await asyncio.to_thread(self._client.link_token_create, request)
        return response.link_token

    async def exchange_public_token(self, public_token: str) -> tuple[str, str]:
        """Exchange a public token for an access token and item ID."""
        request = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = await asyncio.to_thread(
            self._client.item_public_token_exchange, request
        )
        return response.access_token, response.item_id

    async def get_accounts(self, access_token: str) -> list[PlaidAccount]:
        """Get accounts for an item."""
        request = AccountsGetRequest(access_token=access_token)
        response = await asyncio.to_thread(self._client.accounts_get, request)
        return [_parse_account(acc) for acc in response.accounts]

    async def sync_transactions(
        self, access_token: str, cursor: str | None = None
    ) -> PlaidSyncResponse:
        """Sync transactions using cursor-based pagination.

        Args:
            access_token: Plaid access token for the item
            cursor: Optional cursor from previous sync (None for initial sync)

        Returns:
            PlaidSyncResponse with accounts, transactions, and next cursor
        """
        request = TransactionsSyncRequest(
            access_token=access_token,
            cursor=cursor or "",
            count=500,
        )
        response = await asyncio.to_thread(self._client.transactions_sync, request)

        # Parse accounts
        accounts = [_parse_account(acc) for acc in response.accounts]

        # Parse added transactions
        added = [_parse_transaction(tx) for tx in response.added]

        # Parse modified transactions
        modified = [_parse_transaction(tx) for tx in response.modified]

        # Extract removed transaction IDs
        removed = [tx.transaction_id for tx in response.removed]

        # Build raw JSON for logging (simplified representation)
        raw_json = json.dumps({
            "accounts_count": len(accounts),
            "added_count": len(added),
            "modified_count": len(modified),
            "removed_count": len(removed),
            "has_more": response.has_more,
            "next_cursor": response.next_cursor[:20] + "..." if response.next_cursor else None,
        })

        return PlaidSyncResponse(
            accounts=accounts,
            added=added,
            modified=modified,
            removed=removed,
            next_cursor=response.next_cursor,
            has_more=response.has_more,
            raw_json=raw_json,
        )
