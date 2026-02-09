"""Tests for SimpleFIN provider adapter."""

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.clients.simplefin import (
    SFAccount,
    SFSyncResponse,
    SFTransaction,
    _sfin_amount_to_cents,
)
from app.providers.simplefin import SimpleFINProvider

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_simplefin_initial_fixture() -> dict:
    with (FIXTURES_DIR / "simplefin_sync_initial.json").open() as f:
        return json.load(f)


def _fixture_to_sfin_response(fixture: dict) -> SFSyncResponse:
    """Convert fixture JSON to SFSyncResponse for mocking SimpleFINClient."""
    now = int(time.time())
    accounts: list[SFAccount] = []
    transactions: list[SFTransaction] = []

    for acc_data in fixture.get("accounts", []):
        org = acc_data.get("org", {})
        org_name = org.get("name") or org.get("domain")

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
            balance_date=acc_data.get("balance-date"),
            org_name=org_name,
        )
        accounts.append(account)

        for tx_data in acc_data.get("transactions", []):
            posted = tx_data.get("posted", 0)
            pending = posted == 0
            if pending:
                posted = now

            transaction = SFTransaction(
                id=tx_data["id"],
                account_id=acc_data["id"],
                amount=_sfin_amount_to_cents(str(tx_data.get("amount", "0"))),
                date=posted,
                description=tx_data.get("description", ""),
                pending=pending,
                transacted_at=tx_data.get("transacted_at"),
                extra=tx_data.get("extra"),
            )
            transactions.append(transaction)

    return SFSyncResponse(
        accounts=accounts,
        transactions=transactions,
        errors=fixture.get("errors", []),
        raw_json=json.dumps({"accounts_count": len(accounts)}),
    )


class TestSimpleFINProvider:
    """Test the SimpleFIN provider adapter maps SF* -> Provider* correctly."""

    @pytest.mark.asyncio
    async def test_sync_maps_accounts(self):
        """Provider adapter maps SFAccount to ProviderAccount."""
        fixture = load_simplefin_initial_fixture()
        mock_response = _fixture_to_sfin_response(fixture)

        provider = SimpleFINProvider()

        with patch("app.providers.simplefin.SimpleFINClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.fetch_accounts = AsyncMock(return_value=mock_response)

            result = await provider.sync(
                credential_data={"access_url": "https://user:pass@bridge.simplefin.org/simplefin"},
                cursor=None,
            )

        assert len(result.accounts) == 2
        checking = result.accounts[0]
        assert checking.id == "ACT_001"
        assert checking.name == "My Checking"
        assert checking.currency == "USD"
        assert checking.balance_current == 123456
        assert checking.balance_available == 120000
        assert checking.org_name == "First Bank"

    @pytest.mark.asyncio
    async def test_sync_maps_transactions(self):
        """Provider adapter maps SFTransaction to ProviderTransaction."""
        fixture = load_simplefin_initial_fixture()
        mock_response = _fixture_to_sfin_response(fixture)

        provider = SimpleFINProvider()

        with patch("app.providers.simplefin.SimpleFINClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.fetch_accounts = AsyncMock(return_value=mock_response)

            result = await provider.sync(
                credential_data={"access_url": "https://user:pass@bridge.simplefin.org/simplefin"},
                cursor=None,
            )

        assert len(result.transactions) == 3

        amazon = next(t for t in result.transactions if t.id == "TXN_001")
        assert amazon.amount == -5000
        assert amazon.description == "Amazon"
        assert amazon.pending is False
        assert amazon.transacted_at == 1705190400
        assert amazon.extra == {"merchant_id": "AMZN", "category_code": "5411"}

    @pytest.mark.asyncio
    async def test_sync_no_session_data(self):
        """SimpleFIN adapter never returns session_data."""
        fixture = load_simplefin_initial_fixture()
        mock_response = _fixture_to_sfin_response(fixture)

        provider = SimpleFINProvider()

        with patch("app.providers.simplefin.SimpleFINClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.fetch_accounts = AsyncMock(return_value=mock_response)

            result = await provider.sync(
                credential_data={"access_url": "https://user:pass@bridge.simplefin.org/simplefin"},
                cursor=None,
            )

        assert result.session_data is None

    @pytest.mark.asyncio
    async def test_validate_credentials(self):
        """validate_credentials claims token and returns access_url dict."""
        provider = SimpleFINProvider()

        with patch("app.providers.simplefin.SimpleFINClient") as MockClient:
            MockClient.claim_setup_token = AsyncMock(
                return_value="https://user:pass@bridge.simplefin.org/simplefin"
            )

            result = await provider.validate_credentials({"setup_token": "dGVzdA=="})

        assert result == {"access_url": "https://user:pass@bridge.simplefin.org/simplefin"}

    @pytest.mark.asyncio
    async def test_validate_credentials_missing_token(self):
        """validate_credentials raises ProviderError for missing token."""
        from app.providers import ProviderError

        provider = SimpleFINProvider()

        with pytest.raises(ProviderError, match="Missing setup_token"):
            await provider.validate_credentials({})
