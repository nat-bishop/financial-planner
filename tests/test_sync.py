"""Tests for SimpleFIN sync functionality."""

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.clients.simplefin import (
    SFAccount,
    SFSyncResponse,
    SFTransaction,
    _sfin_amount_to_cents,
)
from app.core.encryption import decrypt, encrypt
from app.models import Account, Credential, SyncLog, Transaction
from app.services.sync import sync_accounts

# Load fixture data
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_simplefin_initial_fixture() -> dict:
    with (FIXTURES_DIR / "simplefin_sync_initial.json").open() as f:
        return json.load(f)


def load_simplefin_incremental_fixture() -> dict:
    with (FIXTURES_DIR / "simplefin_sync_incremental.json").open() as f:
        return json.load(f)


class TestEncryption:
    """Test credential encryption."""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypted data can be decrypted back."""
        original = "secret_access_url_12345"
        encrypted = encrypt(original)
        decrypted = decrypt(encrypted)
        assert decrypted == original
        assert encrypted != original


class TestSfinAmountConversion:
    """Test SimpleFIN amount conversion (string decimal parsing)."""

    def test_negative_amount_stays_negative(self):
        """Negative (expense) stays negative — no sign inversion."""
        assert _sfin_amount_to_cents("-50.00") == -5000

    def test_positive_amount_stays_positive(self):
        """Positive (income/deposit) stays positive."""
        assert _sfin_amount_to_cents("1500.00") == 150000

    def test_zero_amount(self):
        """Zero stays zero."""
        assert _sfin_amount_to_cents("0") == 0
        assert _sfin_amount_to_cents("0.00") == 0

    def test_fractional_cents_rounded(self):
        """Fractional cents are rounded correctly using Decimal."""
        assert _sfin_amount_to_cents("-10.155") == -1016  # rounds up (half-up)
        assert _sfin_amount_to_cents("-10.154") == -1015  # rounds down

    def test_precision_preserved(self):
        """Decimal parsing avoids float precision issues."""
        # float("10.15") * 100 = 1014.999... but Decimal gets it right
        assert _sfin_amount_to_cents("10.15") == 1015
        assert _sfin_amount_to_cents("-10.15") == -1015


class TestSimpleFINParsing:
    """Test SimpleFIN response parsing."""

    def test_parse_accounts(self):
        """Accounts are parsed correctly from fixture data."""
        fixture = load_simplefin_initial_fixture()
        response = _fixture_to_sfin_response(fixture)

        assert len(response.accounts) == 2

        # Check checking account
        checking = response.accounts[0]
        assert checking.id == "ACT_001"
        assert checking.name == "My Checking"
        assert checking.balance_current == 123456  # cents
        assert checking.balance_available == 120000  # cents
        assert checking.org_name == "First Bank"
        assert checking.currency == "USD"

        # Check credit card
        credit = response.accounts[1]
        assert credit.id == "ACT_002"
        assert credit.balance_current == -50000  # negative balance (owed)
        assert credit.balance_available is None

    def test_parse_transactions(self):
        """Transactions are parsed correctly — no sign inversion."""
        fixture = load_simplefin_initial_fixture()
        response = _fixture_to_sfin_response(fixture)

        assert len(response.transactions) == 3

        # Check expense (Amazon purchase)
        amazon = next(t for t in response.transactions if t.id == "TXN_001")
        assert amazon.amount == -5000  # -50.00 stays -5000 cents
        assert amazon.description == "Amazon"
        assert amazon.pending is False

        # Check income (Payroll)
        payroll = next(t for t in response.transactions if t.id == "TXN_002")
        assert payroll.amount == 150000  # 1500.00 stays +150000 cents

        # Check pending transaction (posted=0 → pending=True)
        restaurant = next(t for t in response.transactions if t.id == "TXN_003")
        assert restaurant.pending is True
        assert restaurant.date > 0  # posted=0 gets substituted with current time

    def test_parse_transacted_at_and_extra(self):
        """transacted_at and extra are parsed when present, None when absent."""
        fixture = load_simplefin_initial_fixture()
        response = _fixture_to_sfin_response(fixture)

        # TXN_001 has both fields
        txn_001 = next(t for t in response.transactions if t.id == "TXN_001")
        assert txn_001.transacted_at == 1705190400
        assert txn_001.extra == {"merchant_id": "AMZN", "category_code": "5411"}

        # TXN_002 has neither
        txn_002 = next(t for t in response.transactions if t.id == "TXN_002")
        assert txn_002.transacted_at is None
        assert txn_002.extra is None

    def test_parse_errors(self):
        """Error array is captured from response."""
        fixture = load_simplefin_incremental_fixture()
        response = _fixture_to_sfin_response(fixture)

        assert len(response.errors) == 1
        assert "Rate limit" in response.errors[0]


class TestSyncAccounts:
    """Test sync orchestration."""

    @pytest.mark.asyncio
    async def test_sync_creates_accounts_and_transactions(self, db):
        """Sync creates accounts and transactions from SimpleFIN data."""
        cred = Credential(
            id="cred_1",
            provider="simplefin",
            encrypted_data=encrypt(json.dumps({
                "access_url": "https://user:pass@bridge.simplefin.org/simplefin",
            })),
        )
        db.add(cred)
        await db.flush()

        fixture = load_simplefin_initial_fixture()
        mock_response = _fixture_to_sfin_response(fixture)

        with patch("app.services.sync.SimpleFINClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.fetch_accounts = AsyncMock(return_value=mock_response)

            sync_log = await sync_accounts(db)

        assert sync_log.status == "success"
        assert sync_log.accounts_synced == 2
        assert sync_log.transactions_added == 3
        assert sync_log.raw_response is not None

        # Verify accounts were created
        accounts = (await db.scalars(select(Account))).all()
        assert len(accounts) == 2

        # Verify provider is simplefin
        checking = next(a for a in accounts if a.id == "ACT_001")
        assert checking.provider == "simplefin"
        assert checking.org_name == "First Bank"

        # Verify transactions were created
        transactions = (await db.scalars(select(Transaction))).all()
        assert len(transactions) == 3

        # Verify amount convention (no sign inversion)
        amazon_tx = next(t for t in transactions if t.external_id == "TXN_001")
        assert amazon_tx.amount == -5000  # expense is negative

        payroll_tx = next(t for t in transactions if t.external_id == "TXN_002")
        assert payroll_tx.amount == 150000  # income is positive

    @pytest.mark.asyncio
    async def test_sync_stores_transacted_at_and_extra(self, db):
        """Sync stores transacted_at column and extra in raw_data."""
        cred = Credential(
            id="cred_1",
            provider="simplefin",
            encrypted_data=encrypt(json.dumps({
                "access_url": "https://user:pass@bridge.simplefin.org/simplefin",
            })),
        )
        db.add(cred)
        await db.flush()

        fixture = load_simplefin_initial_fixture()
        mock_response = _fixture_to_sfin_response(fixture)

        with patch("app.services.sync.SimpleFINClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.fetch_accounts = AsyncMock(return_value=mock_response)
            await sync_accounts(db)

        # TXN_001 has transacted_at and extra
        tx1 = await db.scalar(
            select(Transaction).where(Transaction.external_id == "TXN_001")
        )
        assert tx1.transacted_at == 1705190400
        raw = json.loads(tx1.raw_data)
        assert raw["extra"]["merchant_id"] == "AMZN"

        # TXN_002 has neither
        tx2 = await db.scalar(
            select(Transaction).where(Transaction.external_id == "TXN_002")
        )
        assert tx2.transacted_at is None
        raw2 = json.loads(tx2.raw_data)
        assert raw2["extra"] is None

    @pytest.mark.asyncio
    async def test_sync_stores_cursor_as_timestamp(self, db):
        """Sync stores current timestamp as cursor."""
        cred = Credential(
            id="cred_1",
            provider="simplefin",
            encrypted_data=encrypt(json.dumps({
                "access_url": "https://user:pass@bridge.simplefin.org/simplefin",
            })),
        )
        db.add(cred)
        await db.flush()

        fixture = load_simplefin_initial_fixture()
        mock_response = _fixture_to_sfin_response(fixture)

        before = int(time.time())

        with patch("app.services.sync.SimpleFINClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.fetch_accounts = AsyncMock(return_value=mock_response)
            await sync_accounts(db)

        cred = await db.get(Credential, "cred_1")
        cursor_ts = int(cred.sync_cursor)
        assert cursor_ts >= before

    @pytest.mark.asyncio
    async def test_sync_logs_simplefin_errors(self, db):
        """SimpleFIN errors array is captured in sync log."""
        cred = Credential(
            id="cred_1",
            provider="simplefin",
            encrypted_data=encrypt(json.dumps({
                "access_url": "https://user:pass@bridge.simplefin.org/simplefin",
            })),
        )
        db.add(cred)
        await db.flush()

        fixture = load_simplefin_incremental_fixture()
        mock_response = _fixture_to_sfin_response(fixture)

        with patch("app.services.sync.SimpleFINClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.fetch_accounts = AsyncMock(return_value=mock_response)
            sync_log = await sync_accounts(db)

        assert sync_log.status == "success"
        assert "Rate limit" in sync_log.error_message

    @pytest.mark.asyncio
    async def test_sync_preserves_user_fields_on_update(self, db):
        """User-set categories are preserved when transaction is re-synced."""
        cred = Credential(
            id="cred_1",
            provider="simplefin",
            encrypted_data=encrypt(json.dumps({
                "access_url": "https://user:pass@bridge.simplefin.org/simplefin",
            })),
        )
        db.add(cred)
        await db.flush()

        # First sync
        fixture1 = load_simplefin_initial_fixture()
        mock_response1 = _fixture_to_sfin_response(fixture1)

        with patch("app.services.sync.SimpleFINClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.fetch_accounts = AsyncMock(return_value=mock_response1)
            await sync_accounts(db)

        # User updates category on TXN_003
        tx = await db.scalar(
            select(Transaction).where(Transaction.external_id == "TXN_003")
        )
        tx.category = "Dining Out"
        tx.notes = "Birthday dinner"
        await db.flush()

        # Second sync — TXN_003 now has real posted date (not pending)
        fixture2 = load_simplefin_incremental_fixture()
        mock_response2 = _fixture_to_sfin_response(fixture2)

        # Need to remove rate limit check for this test
        with (
            patch("app.services.sync.SimpleFINClient") as MockClient,
            patch("app.services.sync.MAX_SYNCS_PER_DAY", 999),
        ):
            mock_instance = MockClient.return_value
            mock_instance.fetch_accounts = AsyncMock(return_value=mock_response2)
            await sync_accounts(db)

        # Refresh
        await db.commit()
        db.expire_all()

        # Verify user fields preserved
        tx = await db.scalar(
            select(Transaction).where(Transaction.external_id == "TXN_003")
        )
        assert tx.category == "Dining Out"  # Preserved
        assert tx.notes == "Birthday dinner"  # Preserved
        assert tx.is_pending is False  # Updated from SimpleFIN

    @pytest.mark.asyncio
    async def test_sync_fails_without_credentials(self, db):
        """Sync fails gracefully when no credentials are configured."""
        sync_log = await sync_accounts(db)

        assert sync_log.status == "failed"
        assert "No SimpleFIN credentials" in sync_log.error_message

    @pytest.mark.asyncio
    async def test_sync_deduplicates_transactions(self, db):
        """Running sync twice doesn't create duplicate transactions."""
        cred = Credential(
            id="cred_1",
            provider="simplefin",
            encrypted_data=encrypt(json.dumps({
                "access_url": "https://user:pass@bridge.simplefin.org/simplefin",
            })),
        )
        db.add(cred)
        await db.flush()

        fixture = load_simplefin_initial_fixture()
        mock_response = _fixture_to_sfin_response(fixture)

        with (
            patch("app.services.sync.SimpleFINClient") as MockClient,
            patch("app.services.sync.MAX_SYNCS_PER_DAY", 999),
        ):
            mock_instance = MockClient.return_value
            mock_instance.fetch_accounts = AsyncMock(return_value=mock_response)

            # First sync
            sync_log1 = await sync_accounts(db)
            assert sync_log1.transactions_added == 3

            # Second sync - same transactions
            sync_log2 = await sync_accounts(db)
            assert sync_log2.transactions_added == 3  # counts synced

        # Key assertion: still only 3 transactions (upsert, not insert)
        transactions = (await db.scalars(select(Transaction))).all()
        assert len(transactions) == 3

    @pytest.mark.asyncio
    async def test_sync_rate_limited(self, db):
        """Sync rejects if daily limit (24 syncs) is reached."""
        now = int(time.time())
        for i in range(24):
            db.add(SyncLog(
                started_at=now - (i * 100),
                completed_at=now - (i * 100),
                status="success",
            ))
        await db.flush()

        cred = Credential(
            id="cred_1",
            provider="simplefin",
            encrypted_data=encrypt(json.dumps({
                "access_url": "https://user:pass@bridge.simplefin.org/simplefin",
            })),
        )
        db.add(cred)
        await db.flush()

        with pytest.raises(RuntimeError, match="Daily limit reached"):
            await sync_accounts(db)


class TestTransactionUpdate:
    """Test transaction editing."""

    @pytest.mark.asyncio
    async def test_update_transaction_category(self, db):
        """Transaction category can be updated."""
        account = Account(
            id="act_1",
            provider="simplefin",
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


def _fixture_to_sfin_response(fixture: dict) -> SFSyncResponse:
    """Convert fixture JSON to SFSyncResponse."""
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
        raw_json=json.dumps({
            "accounts_count": len(accounts),
            "errors": fixture.get("errors", []),
        }),
    )
