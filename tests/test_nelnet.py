"""Tests for Nelnet provider data transformation (pure functions)."""

from app.providers.nelnet import (
    NelnetAccountData,
    NelnetPaymentData,
    _parse_currency,
    _parse_date,
    _stable_id,
    _to_provider_accounts,
    _to_provider_transactions,
)


class TestParseCurrency:
    def test_positive_amount(self):
        assert _parse_currency("$1,234.56") == 123456

    def test_negative_amount(self):
        assert _parse_currency("-$50.00") == -5000

    def test_parenthetical_negative(self):
        assert _parse_currency("($100.00)") == -10000

    def test_plain_number(self):
        assert _parse_currency("250.00") == 25000

    def test_zero(self):
        assert _parse_currency("$0.00") == 0

    def test_empty_string(self):
        assert _parse_currency("") == 0

    def test_dash(self):
        assert _parse_currency("--") == 0


class TestParseDate:
    def test_valid_date(self):
        ts = _parse_date("01/15/2025")
        assert ts > 0
        # Jan 15, 2025 UTC
        assert ts == 1736899200

    def test_invalid_date_returns_now(self):
        ts = _parse_date("not-a-date")
        assert ts > 0  # Falls back to current time


class TestStableId:
    def test_deterministic(self):
        id1 = _stable_id("nelnet", "account", "My Loan")
        id2 = _stable_id("nelnet", "account", "My Loan")
        assert id1 == id2

    def test_different_inputs(self):
        id1 = _stable_id("nelnet", "account", "Loan A")
        id2 = _stable_id("nelnet", "account", "Loan B")
        assert id1 != id2


class TestToProviderAccounts:
    def test_maps_account_data(self):
        scraped = [
            NelnetAccountData(
                group_name="Group: AA",
                loan_type="DIRECT SUB",
                status="REPAYMENT",
                outstanding_balance="$3,490.45",
                interest_rate="3.510%",
            ),
        ]
        accounts = _to_provider_accounts(scraped)
        assert len(accounts) == 1
        a = accounts[0]
        assert a.name == "Nelnet Group: AA - DIRECT SUB"
        assert a.currency == "USD"
        assert a.balance_current == -349045
        assert a.account_type == "loan/student"
        assert len(a.id) == 16  # sha256 hex truncated

    def test_multiple_accounts(self):
        scraped = [
            NelnetAccountData(
                group_name="Group: AA",
                loan_type="DIRECT SUB",
                status="REPAYMENT",
                outstanding_balance="$1,000.00",
            ),
            NelnetAccountData(
                group_name="Group: AB",
                loan_type="DIRECT UNSUB",
                status="REPAYMENT",
                outstanding_balance="$2,000.00",
            ),
        ]
        accounts = _to_provider_accounts(scraped)
        assert len(accounts) == 2
        assert accounts[0].id != accounts[1].id


class TestToProviderTransactions:
    def test_maps_payment_data(self):
        accounts = [
            NelnetAccountData(
                group_name="Group: AA",
                loan_type="DIRECT SUB",
                status="REPAYMENT",
                outstanding_balance="$3,490.45",
            ),
        ]
        scraped = [
            NelnetPaymentData(
                date="01/28/2026",
                amount="$266.83",
                principal="$248.66",
                interest="$18.17",
                payment_type="Auto Debit",
            ),
        ]
        transactions = _to_provider_transactions(accounts, scraped)
        assert len(transactions) == 1
        t = transactions[0]
        assert t.amount == -26683  # Payments are expenses (negative)
        assert t.description == "Nelnet Auto Debit Payment"
        assert t.pending is False
        assert t.extra == {
            "principal": "$248.66",
            "interest": "$18.17",
            "payment_type": "Auto Debit",
        }

    def test_payment_already_negative(self):
        """Negative amount stays negative."""
        scraped = [
            NelnetPaymentData(
                date="01/15/2025",
                amount="-$250.00",
                principal="$200.00",
                interest="$50.00",
                payment_type="Electronic",
            ),
        ]
        transactions = _to_provider_transactions([], scraped)
        assert transactions[0].amount == -25000

    def test_empty_payments(self):
        transactions = _to_provider_transactions([], [])
        assert transactions == []

    def test_links_to_first_account(self):
        accounts = [
            NelnetAccountData(
                group_name="Group: AA",
                loan_type="DIRECT SUB",
                status="REPAYMENT",
                outstanding_balance="$1,000.00",
            ),
            NelnetAccountData(
                group_name="Group: AB",
                loan_type="DIRECT UNSUB",
                status="REPAYMENT",
                outstanding_balance="$2,000.00",
            ),
        ]
        scraped = [
            NelnetPaymentData(
                date="01/28/2026",
                amount="$100.00",
                principal="$80.00",
                interest="$20.00",
                payment_type="Electronic",
            ),
        ]
        transactions = _to_provider_transactions(accounts, scraped)
        # Transaction should link to the first account
        expected_id = _stable_id("nelnet", "account", "Group: AA")
        assert transactions[0].account_id == expected_id
