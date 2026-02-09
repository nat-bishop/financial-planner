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
                name="Federal Subsidized",
                balance="$12,345.67",
                interest_rate="4.5%",
                status="In Repayment",
            ),
        ]
        accounts = _to_provider_accounts(scraped)
        assert len(accounts) == 1
        a = accounts[0]
        assert a.name == "Federal Subsidized"
        assert a.currency == "USD"
        assert a.balance_current == 1234567
        assert a.account_type == "loan/student"
        assert len(a.id) == 16  # sha256 hex truncated

    def test_multiple_accounts(self):
        scraped = [
            NelnetAccountData(name="Loan A", balance="$1,000.00"),
            NelnetAccountData(name="Loan B", balance="$2,000.00"),
        ]
        accounts = _to_provider_accounts(scraped)
        assert len(accounts) == 2
        assert accounts[0].id != accounts[1].id


class TestToProviderTransactions:
    def test_maps_payment_data(self):
        scraped = [
            NelnetPaymentData(
                date="01/15/2025",
                description="Monthly Payment",
                amount="$250.00",
                principal="$200.00",
                interest="$50.00",
            ),
        ]
        transactions = _to_provider_transactions(scraped)
        assert len(transactions) == 1
        t = transactions[0]
        assert t.amount == -25000  # Payments are expenses (negative)
        assert t.description == "Monthly Payment"
        assert t.pending is False
        assert t.extra == {"principal": "$200.00", "interest": "$50.00"}

    def test_payment_already_negative(self):
        """Negative amount stays negative."""
        scraped = [
            NelnetPaymentData(
                date="01/15/2025",
                description="Payment",
                amount="-$250.00",
            ),
        ]
        transactions = _to_provider_transactions(scraped)
        assert transactions[0].amount == -25000

    def test_empty_payments(self):
        transactions = _to_provider_transactions([])
        assert transactions == []
