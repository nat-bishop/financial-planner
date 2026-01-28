"""Tests for sync functionality."""

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.encryption import decrypt, encrypt
from app.models import Account, Credential, SyncLog, Transaction
from app.simplefin import SimpleFINClient, SimpleFINResponse, SimpleFINAccount
from app.sync import sync_accounts


# Load fixture data
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_simplefin_fixture() -> dict:
    with open(FIXTURES_DIR / "simplefin_response.json") as f:
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


class TestSimpleFINClient:
    """Test SimpleFIN client parsing."""

    def test_parse_accounts(self):
        """SimpleFIN response is parsed correctly."""
        fixture = load_simplefin_fixture()

        # Simulate what the client does
        accounts = []
        for org in fixture.get("accounts", []):
            org_domain = org.get("org", {}).get("domain", "unknown")
            org_name = org.get("org", {}).get("name")

            balance = int(float(org.get("balance", 0)) * 100)
            available = (
                int(float(org.get("available-balance")) * 100)
                if org.get("available-balance")
                else None
            )

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

        assert len(accounts) == 2

        # Check first account
        chase = accounts[0]
        assert chase.id == "ACT_001"
        assert chase.org_domain == "chase.com"
        assert chase.org_name == "Chase"
        assert chase.name == "Chase Checking"
        assert chase.balance == 123456  # cents
        assert chase.available_balance == 120000  # cents
        assert len(chase.transactions) == 3

        # Check second account
        amex = accounts[1]
        assert amex.id == "ACT_002"
        assert amex.org_domain == "amex.com"
        assert amex.balance == -50000  # negative for credit card


class TestSyncAccounts:
    """Test sync orchestration."""

    @pytest.mark.asyncio
    async def test_sync_creates_accounts_and_transactions(self, db):
        """Sync creates accounts and transactions from SimpleFIN data."""
        # Setup: create credentials
        cred = Credential(
            id="cred_1",
            provider="simplefin",
            encrypted_data=encrypt(json.dumps({"access_url": "https://test"})),
        )
        db.add(cred)
        await db.flush()

        # Mock SimpleFIN client
        fixture = load_simplefin_fixture()
        mock_response = _fixture_to_response(fixture)

        with patch.object(
            SimpleFINClient, "fetch_accounts", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = mock_response

            sync_log = await sync_accounts(db)

        assert sync_log.status == "success"
        assert sync_log.accounts_synced == 2
        assert sync_log.transactions_added == 5
        assert sync_log.transactions_updated == 0
        assert sync_log.raw_response is not None

        # Verify accounts were created
        accounts = (await db.scalars(select(Account))).all()
        assert len(accounts) == 2

        # Verify transactions were created
        transactions = (await db.scalars(select(Transaction))).all()
        assert len(transactions) == 5

    @pytest.mark.asyncio
    async def test_sync_deduplicates_transactions(self, db):
        """Running sync twice doesn't create duplicate transactions."""
        # Setup: create credentials
        cred = Credential(
            id="cred_1",
            provider="simplefin",
            encrypted_data=encrypt(json.dumps({"access_url": "https://test"})),
        )
        db.add(cred)
        await db.flush()

        fixture = load_simplefin_fixture()
        mock_response = _fixture_to_response(fixture)

        with patch.object(
            SimpleFINClient, "fetch_accounts", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = mock_response

            # First sync
            sync_log1 = await sync_accounts(db)
            assert sync_log1.transactions_added == 5
            assert sync_log1.transactions_updated == 0

            # Second sync - should update, not add
            sync_log2 = await sync_accounts(db)
            assert sync_log2.transactions_added == 0
            assert sync_log2.transactions_updated == 5

        # Still only 5 transactions
        transactions = (await db.scalars(select(Transaction))).all()
        assert len(transactions) == 5

    @pytest.mark.asyncio
    async def test_sync_fails_without_credentials(self, db):
        """Sync fails gracefully when no credentials are configured."""
        sync_log = await sync_accounts(db)

        assert sync_log.status == "failed"
        assert "No SimpleFIN credentials" in sync_log.error_message

    @pytest.mark.asyncio
    async def test_sync_stores_raw_response(self, db):
        """Sync stores the raw SimpleFIN JSON for debugging."""
        cred = Credential(
            id="cred_1",
            provider="simplefin",
            encrypted_data=encrypt(json.dumps({"access_url": "https://test"})),
        )
        db.add(cred)
        await db.flush()

        fixture = load_simplefin_fixture()
        mock_response = _fixture_to_response(fixture)

        with patch.object(
            SimpleFINClient, "fetch_accounts", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = mock_response
            await sync_accounts(db)

        sync_log = await db.scalar(select(SyncLog).order_by(SyncLog.id.desc()))
        assert sync_log.raw_response is not None

        # Verify it's valid JSON
        raw_data = json.loads(sync_log.raw_response)
        assert "accounts" in raw_data


class TestTransactionUpdate:
    """Test transaction editing."""

    @pytest.mark.asyncio
    async def test_update_transaction_category(self, db):
        """Transaction category can be updated."""
        # Create account and transaction
        account = Account(
            id="act_1",
            provider="simplefin",
            org_domain="test.com",
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


def _fixture_to_response(fixture: dict) -> SimpleFINResponse:
    """Convert fixture JSON to SimpleFINResponse."""
    accounts = []
    for org in fixture.get("accounts", []):
        balance = int(float(org.get("balance", 0)) * 100)
        available = (
            int(float(org.get("available-balance")) * 100)
            if org.get("available-balance")
            else None
        )

        account = SimpleFINAccount(
            id=org.get("id"),
            org_domain=org.get("org", {}).get("domain", "unknown"),
            org_name=org.get("org", {}).get("name"),
            name=org.get("name", "Unknown Account"),
            currency=org.get("currency", "USD"),
            balance=balance,
            available_balance=available,
            balance_date=org.get("balance-date", 0),
            transactions=org.get("transactions", []),
        )
        accounts.append(account)

    return SimpleFINResponse(accounts=accounts, raw_json=json.dumps(fixture))
