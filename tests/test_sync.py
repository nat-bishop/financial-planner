"""Tests for Plaid sync functionality."""

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.encryption import decrypt, encrypt
from app.models import Account, Credential, Transaction
from app.plaid import (
    PlaidAccount,
    PlaidSyncResponse,
    PlaidTransaction,
    _plaid_amount_to_cents,
    _plaid_date_to_timestamp,
)
from app.sync import sync_accounts

# Load fixture data
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_plaid_initial_fixture() -> dict:
    with (FIXTURES_DIR / "plaid_sync_initial.json").open() as f:
        return json.load(f)


def load_plaid_incremental_fixture() -> dict:
    with (FIXTURES_DIR / "plaid_sync_incremental.json").open() as f:
        return json.load(f)


class TestEncryption:
    """Test credential encryption."""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypted data can be decrypted back."""
        original = "secret_access_token_12345"
        encrypted = encrypt(original)
        decrypted = decrypt(encrypted)
        assert decrypted == original
        assert encrypted != original


class TestPlaidAmountConversion:
    """Test Plaid amount conversion (critical - sign inversion)."""

    def test_positive_amount_becomes_negative(self):
        """Plaid positive (expense) becomes our negative."""
        # Plaid: 50.00 means money out (expense)
        # Our convention: negative means expense
        assert _plaid_amount_to_cents(50.00) == -5000

    def test_negative_amount_becomes_positive(self):
        """Plaid negative (income) becomes our positive."""
        # Plaid: -1500.00 means money in (income/deposit)
        # Our convention: positive means income
        assert _plaid_amount_to_cents(-1500.00) == 150000

    def test_zero_amount(self):
        """Zero stays zero."""
        assert _plaid_amount_to_cents(0) == 0

    def test_fractional_cents_rounded(self):
        """Fractional cents are rounded."""
        assert _plaid_amount_to_cents(10.005) == -1001  # rounds up
        assert _plaid_amount_to_cents(10.004) == -1000  # rounds down


class TestPlaidDateConversion:
    """Test Plaid date conversion."""

    def test_date_string_to_timestamp(self):
        """YYYY-MM-DD becomes Unix timestamp (local time)."""
        from datetime import datetime

        # The conversion uses local time, so we verify by converting back
        timestamp = _plaid_date_to_timestamp("2024-01-15")
        # Convert back and check the date portion
        dt = datetime.fromtimestamp(timestamp)
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15


class TestPlaidClientParsing:
    """Test Plaid response parsing."""

    def test_parse_accounts(self):
        """Accounts are parsed correctly from fixture data."""
        fixture = load_plaid_initial_fixture()

        accounts = []
        for acc in fixture["accounts"]:
            balances = acc["balances"]
            account = PlaidAccount(
                id=acc["account_id"],
                name=acc["name"],
                official_name=acc.get("official_name"),
                type=acc["type"],
                subtype=acc.get("subtype"),
                mask=acc.get("mask"),
                balance_current=int(balances["current"] * 100),
                balance_available=int(balances["available"] * 100) if balances.get("available") else None,
                currency=balances.get("iso_currency_code", "USD"),
            )
            accounts.append(account)

        assert len(accounts) == 2

        # Check checking account
        checking = accounts[0]
        assert checking.id == "ACT_001"
        assert checking.name == "Plaid Checking"
        assert checking.official_name == "Plaid Gold Checking"
        assert checking.type == "depository"
        assert checking.subtype == "checking"
        assert checking.balance_current == 123456  # cents
        assert checking.balance_available == 120000  # cents

        # Check credit card
        credit = accounts[1]
        assert credit.id == "ACT_002"
        assert credit.type == "credit"
        assert credit.subtype == "credit card"
        assert credit.balance_current == 50000  # cents (positive in Plaid for owed amount)
        assert credit.balance_available is None

    def test_parse_transactions(self):
        """Transactions are parsed correctly with amount inversion."""
        fixture = load_plaid_initial_fixture()

        transactions = []
        for tx in fixture["added"]:
            transaction = PlaidTransaction(
                id=tx["transaction_id"],
                account_id=tx["account_id"],
                amount=_plaid_amount_to_cents(tx["amount"]),
                date=_plaid_date_to_timestamp(tx["date"]),
                description=tx.get("merchant_name") or tx.get("name", ""),
                pending=tx["pending"],
                category=tx.get("personal_finance_category", {}).get("primary"),
            )
            transactions.append(transaction)

        assert len(transactions) == 3

        # Check expense (Amazon purchase)
        amazon = transactions[0]
        assert amazon.id == "TXN_001"
        assert amazon.amount == -5000  # Plaid 50.00 -> -5000 cents (expense)
        assert amazon.description == "Amazon"
        assert amazon.category == "SHOPPING"
        assert amazon.pending is False

        # Check income (Payroll)
        payroll = transactions[1]
        assert payroll.id == "TXN_002"
        assert payroll.amount == 150000  # Plaid -1500.00 -> +150000 cents (income)
        assert payroll.description == "PAYROLL"
        assert payroll.category == "INCOME"

        # Check pending transaction
        restaurant = transactions[2]
        assert restaurant.id == "TXN_003"
        assert restaurant.pending is True
        assert restaurant.category == "FOOD_AND_DRINK"


class TestSyncAccounts:
    """Test sync orchestration."""

    @pytest.mark.asyncio
    async def test_sync_creates_accounts_and_transactions(self, db):
        """Sync creates accounts and transactions from Plaid data."""
        # Setup: create credentials
        cred = Credential(
            id="cred_1",
            provider="plaid",
            encrypted_data=encrypt(json.dumps({
                "access_token": "access-sandbox-test",
                "item_id": "item_test",
            })),
        )
        db.add(cred)
        await db.flush()

        # Mock Plaid client
        fixture = load_plaid_initial_fixture()
        mock_response = _fixture_to_plaid_response(fixture)

        with patch("app.sync.PlaidClient") as MockPlaidClient:
            mock_client = MockPlaidClient.return_value
            mock_client.sync_transactions = AsyncMock(return_value=mock_response)

            sync_log = await sync_accounts(db)

        assert sync_log.status == "success"
        assert sync_log.accounts_synced == 2
        assert sync_log.transactions_added == 3
        assert sync_log.transactions_updated == 0
        assert sync_log.raw_response is not None

        # Verify accounts were created
        accounts = (await db.scalars(select(Account))).all()
        assert len(accounts) == 2

        # Verify account types include subtype
        checking = next(a for a in accounts if a.id == "ACT_001")
        assert checking.account_type == "depository/checking"
        assert checking.org_domain is None  # Plaid doesn't provide this

        # Verify transactions were created
        transactions = (await db.scalars(select(Transaction))).all()
        assert len(transactions) == 3

        # Verify amount conversion
        amazon_tx = next(t for t in transactions if t.external_id == "TXN_001")
        assert amazon_tx.amount == -5000  # expense is negative

        payroll_tx = next(t for t in transactions if t.external_id == "TXN_002")
        assert payroll_tx.amount == 150000  # income is positive

    @pytest.mark.asyncio
    async def test_sync_stores_plaid_category(self, db):
        """New transactions get Plaid's category populated."""
        cred = Credential(
            id="cred_1",
            provider="plaid",
            encrypted_data=encrypt(json.dumps({
                "access_token": "access-sandbox-test",
                "item_id": "item_test",
            })),
        )
        db.add(cred)
        await db.flush()

        fixture = load_plaid_initial_fixture()
        mock_response = _fixture_to_plaid_response(fixture)

        with patch("app.sync.PlaidClient") as MockPlaidClient:
            mock_client = MockPlaidClient.return_value
            mock_client.sync_transactions = AsyncMock(return_value=mock_response)
            await sync_accounts(db)

        # Verify Plaid categories were stored
        transactions = (await db.scalars(select(Transaction))).all()

        amazon_tx = next(t for t in transactions if t.external_id == "TXN_001")
        assert amazon_tx.category == "SHOPPING"

        payroll_tx = next(t for t in transactions if t.external_id == "TXN_002")
        assert payroll_tx.category == "INCOME"

    @pytest.mark.asyncio
    async def test_sync_uses_cursor_for_incremental(self, db):
        """Second sync uses stored cursor."""
        cred = Credential(
            id="cred_1",
            provider="plaid",
            encrypted_data=encrypt(json.dumps({
                "access_token": "access-sandbox-test",
                "item_id": "item_test",
            })),
        )
        db.add(cred)
        await db.flush()

        # First sync
        fixture1 = load_plaid_initial_fixture()
        mock_response1 = _fixture_to_plaid_response(fixture1)

        with patch("app.sync.PlaidClient") as MockPlaidClient:
            mock_client = MockPlaidClient.return_value
            mock_client.sync_transactions = AsyncMock(return_value=mock_response1)
            await sync_accounts(db)

            # Verify cursor was stored
            cred = await db.get(Credential, "cred_1")
            assert cred.sync_cursor == "cursor_page1"

        # Second sync with incremental response
        fixture2 = load_plaid_incremental_fixture()
        mock_response2 = _fixture_to_plaid_response(fixture2)

        with patch("app.sync.PlaidClient") as MockPlaidClient:
            mock_client = MockPlaidClient.return_value
            mock_client.sync_transactions = AsyncMock(return_value=mock_response2)

            sync_log = await sync_accounts(db)

            # Verify cursor was passed
            mock_client.sync_transactions.assert_called_once()
            call_args = mock_client.sync_transactions.call_args
            assert call_args[0][1] == "cursor_page1"  # cursor argument

        assert sync_log.status == "success"
        assert sync_log.transactions_added == 1  # TXN_004
        assert sync_log.transactions_updated == 1  # TXN_003 modified

    @pytest.mark.asyncio
    async def test_sync_removes_deleted_transactions(self, db):
        """Removed transactions are deleted from database."""
        cred = Credential(
            id="cred_1",
            provider="plaid",
            encrypted_data=encrypt(json.dumps({
                "access_token": "access-sandbox-test",
                "item_id": "item_test",
            })),
        )
        db.add(cred)
        await db.flush()

        # First sync - creates 3 transactions
        fixture1 = load_plaid_initial_fixture()
        mock_response1 = _fixture_to_plaid_response(fixture1)

        with patch("app.sync.PlaidClient") as MockPlaidClient:
            mock_client = MockPlaidClient.return_value
            mock_client.sync_transactions = AsyncMock(return_value=mock_response1)
            await sync_accounts(db)

        transactions = (await db.scalars(select(Transaction))).all()
        assert len(transactions) == 3

        # Second sync - removes TXN_001
        fixture2 = load_plaid_incremental_fixture()
        mock_response2 = _fixture_to_plaid_response(fixture2)

        with patch("app.sync.PlaidClient") as MockPlaidClient:
            mock_client = MockPlaidClient.return_value
            mock_client.sync_transactions = AsyncMock(return_value=mock_response2)
            await sync_accounts(db)

        # TXN_001 should be gone, TXN_004 added = still 3 total
        transactions = (await db.scalars(select(Transaction))).all()
        assert len(transactions) == 3

        # Verify TXN_001 is gone
        external_ids = [t.external_id for t in transactions]
        assert "TXN_001" not in external_ids
        assert "TXN_004" in external_ids

    @pytest.mark.asyncio
    async def test_sync_preserves_user_category_on_modified(self, db):
        """User-set categories are preserved when transaction is modified."""
        cred = Credential(
            id="cred_1",
            provider="plaid",
            encrypted_data=encrypt(json.dumps({
                "access_token": "access-sandbox-test",
                "item_id": "item_test",
            })),
        )
        db.add(cred)
        await db.flush()

        # First sync
        fixture1 = load_plaid_initial_fixture()
        mock_response1 = _fixture_to_plaid_response(fixture1)

        with patch("app.sync.PlaidClient") as MockPlaidClient:
            mock_client = MockPlaidClient.return_value
            mock_client.sync_transactions = AsyncMock(return_value=mock_response1)
            await sync_accounts(db)

        # User updates category on TXN_003
        tx = await db.scalar(
            select(Transaction).where(Transaction.external_id == "TXN_003")
        )
        tx.category = "Dining Out"  # User's custom category
        tx.notes = "Birthday dinner"
        await db.flush()

        # Second sync modifies TXN_003 (pending -> not pending)
        fixture2 = load_plaid_incremental_fixture()
        mock_response2 = _fixture_to_plaid_response(fixture2)

        with patch("app.sync.PlaidClient") as MockPlaidClient:
            mock_client = MockPlaidClient.return_value
            mock_client.sync_transactions = AsyncMock(return_value=mock_response2)
            await sync_accounts(db)

        # Refresh the session to get updated data
        await db.commit()
        # Expire all objects to force refresh from DB
        db.expire_all()

        # Verify user fields preserved
        tx = await db.scalar(
            select(Transaction).where(Transaction.external_id == "TXN_003")
        )
        assert tx.category == "Dining Out"  # Preserved
        assert tx.notes == "Birthday dinner"  # Preserved
        assert tx.is_pending is False  # Updated from Plaid

    @pytest.mark.asyncio
    async def test_sync_fails_without_credentials(self, db):
        """Sync fails gracefully when no credentials are configured."""
        sync_log = await sync_accounts(db)

        assert sync_log.status == "failed"
        assert "No Plaid credentials" in sync_log.error_message

    @pytest.mark.asyncio
    async def test_sync_deduplicates_transactions(self, db):
        """Running sync twice doesn't create duplicate transactions."""
        cred = Credential(
            id="cred_1",
            provider="plaid",
            encrypted_data=encrypt(json.dumps({
                "access_token": "access-sandbox-test",
                "item_id": "item_test",
            })),
        )
        db.add(cred)
        await db.flush()

        fixture = load_plaid_initial_fixture()
        mock_response = _fixture_to_plaid_response(fixture)

        with patch("app.sync.PlaidClient") as MockPlaidClient:
            mock_client = MockPlaidClient.return_value
            mock_client.sync_transactions = AsyncMock(return_value=mock_response)

            # First sync
            sync_log1 = await sync_accounts(db)
            assert sync_log1.transactions_added == 3

            # Reset cursor to simulate re-fetching same data
            cred = await db.get(Credential, "cred_1")
            cred.sync_cursor = None
            await db.flush()

            # Second sync - same transactions
            sync_log2 = await sync_accounts(db)
            assert sync_log2.transactions_added == 3  # counts synced

        # Key assertion: still only 3 transactions (upsert, not insert)
        transactions = (await db.scalars(select(Transaction))).all()
        assert len(transactions) == 3


class TestTransactionUpdate:
    """Test transaction editing."""

    @pytest.mark.asyncio
    async def test_update_transaction_category(self, db):
        """Transaction category can be updated."""
        # Create account and transaction
        account = Account(
            id="act_1",
            provider="plaid",
            org_domain=None,
            name="Test Account",
        )
        db.add(account)
        await db.flush()

        tx = Transaction(
            account_id="act_1",
            external_id="tx_1",
            posted_at=int(time.time()),
            amount=-5000,
            description="Test transaction",
        )
        db.add(tx)
        await db.flush()

        # Update category
        tx.category = "Food & Dining"
        tx.subcategory = "Coffee Shops"
        tx.updated_at = int(time.time())
        await db.flush()

        # Verify
        updated_tx = await db.get(Transaction, tx.id)
        assert updated_tx.category == "Food & Dining"
        assert updated_tx.subcategory == "Coffee Shops"
        assert updated_tx.updated_at is not None


def _fixture_to_plaid_response(fixture: dict) -> PlaidSyncResponse:
    """Convert fixture JSON to PlaidSyncResponse."""
    accounts = []
    for acc in fixture.get("accounts", []):
        balances = acc["balances"]
        account = PlaidAccount(
            id=acc["account_id"],
            name=acc["name"],
            official_name=acc.get("official_name"),
            type=acc["type"],
            subtype=acc.get("subtype"),
            mask=acc.get("mask"),
            balance_current=int(balances["current"] * 100),
            balance_available=int(balances["available"] * 100) if balances.get("available") else None,
            currency=balances.get("iso_currency_code", "USD"),
        )
        accounts.append(account)

    added = []
    for tx in fixture.get("added", []):
        transaction = PlaidTransaction(
            id=tx["transaction_id"],
            account_id=tx["account_id"],
            amount=_plaid_amount_to_cents(tx["amount"]),
            date=_plaid_date_to_timestamp(tx["date"]),
            description=tx.get("merchant_name") or tx.get("name", ""),
            pending=tx["pending"],
            category=tx.get("personal_finance_category", {}).get("primary"),
        )
        added.append(transaction)

    modified = []
    for tx in fixture.get("modified", []):
        transaction = PlaidTransaction(
            id=tx["transaction_id"],
            account_id=tx["account_id"],
            amount=_plaid_amount_to_cents(tx["amount"]),
            date=_plaid_date_to_timestamp(tx["date"]),
            description=tx.get("merchant_name") or tx.get("name", ""),
            pending=tx["pending"],
            category=tx.get("personal_finance_category", {}).get("primary"),
        )
        modified.append(transaction)

    removed = [tx["transaction_id"] for tx in fixture.get("removed", [])]

    return PlaidSyncResponse(
        accounts=accounts,
        added=added,
        modified=modified,
        removed=removed,
        next_cursor=fixture.get("next_cursor", ""),
        has_more=fixture.get("has_more", False),
        raw_json=json.dumps(fixture),
    )
