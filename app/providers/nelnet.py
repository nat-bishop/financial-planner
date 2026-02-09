"""Nelnet student loan provider — browser-based scraping.

Two layers for testability:
1. Scraper methods (_login, _scrape_*) — interact with Playwright
2. Data transformation (_to_provider_*) — pure functions, tested with fixtures
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.providers.base import AuthenticationError, ProviderError
from app.providers.browser import BrowserProvider
from app.providers.models import ProviderAccount, ProviderTransaction, SyncResult

if TYPE_CHECKING:
    from playwright.async_api import Page

log = logging.getLogger(__name__)

NELNET_BASE_URL = "https://nelnet.studentaid.gov"
NELNET_LOGIN_URL = f"{NELNET_BASE_URL}/account/login"
NELNET_AUTH_DOMAIN = "auth.nelnet.studentaid.gov"


@dataclass
class NelnetAccountData:
    """Raw scraped account data."""

    name: str
    balance: str  # e.g., "$12,345.67"
    interest_rate: str | None = None
    status: str | None = None


@dataclass
class NelnetPaymentData:
    """Raw scraped payment data."""

    date: str  # e.g., "01/15/2025"
    description: str
    amount: str  # e.g., "$250.00"
    principal: str | None = None
    interest: str | None = None


class NelnetProvider(BrowserProvider):
    provider_name = "nelnet"
    display_name = "Nelnet Student Loans"
    max_syncs_per_day = 4

    async def validate_credentials(self, raw_input: dict) -> dict:
        username = raw_input.get("username", "").strip()
        password = raw_input.get("password", "")
        if not username or not password:
            raise ProviderError(
                "Username and password are required",
                self.provider_name,
            )
        return {"username": username, "password": password}

    async def sync(
        self,
        credential_data: dict,
        cursor: str | None,
        session_data: dict | None = None,
    ) -> SyncResult:
        try:
            return await self._do_sync(credential_data, cursor, session_data)
        except (AuthenticationError, ProviderError):
            raise
        except Exception as e:
            if "timeout" in str(e).lower():
                raise ProviderError(
                    "Browser operation timed out. The site may be slow or unresponsive.",
                    self.provider_name,
                    detail={"error": str(e)},
                ) from e
            raise ProviderError(
                f"Browser error: {e}",
                self.provider_name,
            ) from e

    async def _do_sync(
        self,
        credential_data: dict,
        cursor: str | None,
        session_data: dict | None = None,
    ) -> SyncResult:
        async with self._browser_session(session_data) as (page, context):
            # Navigate to login page
            await page.goto(NELNET_LOGIN_URL, wait_until="load")
            await self._random_delay(1000, 2000)

            # Check if we need to log in (on login page or auth domain)
            if self._needs_login(page):
                log.info("Session expired, logging in")
                await self._login(page, credential_data)

            # Scrape data
            raw_accounts = await self._scrape_accounts(page)
            raw_payments = await self._scrape_payments(page)

            # Save session for next time
            session = await context.storage_state()

            return SyncResult(
                accounts=_to_provider_accounts(raw_accounts),
                transactions=_to_provider_transactions(raw_payments),
                session_data=session,
            )

    def _needs_login(self, page: Page) -> bool:
        """Check if the current page is a login/auth page."""
        url = page.url.lower()
        return (
            NELNET_AUTH_DOMAIN in url
            or "/account/login" in url
            or "/Account/Login" in page.url
        )

    async def _dismiss_consent_overlay(self, page: Page) -> None:
        """Remove Transcend consent manager overlay that blocks clicks."""
        await page.evaluate("""() => {
            const el = document.getElementById('transcend-consent-manager');
            if (el) el.remove();
        }""")

    async def _login(self, page: Page, creds: dict) -> None:
        """Handle Nelnet's login flow (same-tab redirect, not popup).

        Flow (verified against real site):
        1. Login page: dismiss consent overlay, click "Continue" (borrower)
        2. Federal disclaimer: click "Accept"
        3. Redirects to auth.nelnet.studentaid.gov/Account/Login
        4. Fill username (#username-textfield) and password (#password-textfield)
        5. Click "Continue" to submit
        6. Handle 2FA if prompted, then redirect back to main site
        """
        try:
            # Step 1: Dismiss consent overlay and click Continue
            await self._dismiss_consent_overlay(page)
            await self._random_delay(300, 600)

            continue_btn = page.get_by_role("button", name="Continue")
            await continue_btn.wait_for(timeout=30_000)
            await continue_btn.click()
            await self._random_delay(500, 1000)

            # Step 2: Accept federal disclaimer
            accept_btn = page.get_by_role("button", name="Accept")
            await accept_btn.click(timeout=10_000)
            await self._random_delay(1000, 2000)

            # Step 3: Wait for redirect to auth page
            await page.wait_for_url(
                f"**{NELNET_AUTH_DOMAIN}/**", timeout=30_000
            )
            await page.wait_for_load_state("load")
            await self._random_delay(500, 1000)

            # Step 4: Fill credentials
            username_field = "#username-textfield"
            password_field = "#password-textfield"

            await page.wait_for_selector(username_field, timeout=15_000)

            await self._type_like_human(page, username_field, creds["username"])
            await self._random_delay(200, 500)
            await self._type_like_human(page, password_field, creds["password"])
            await self._random_delay(300, 700)

            # Step 5: Submit login
            await page.get_by_role("button", name="Continue").click()
            await self._random_delay(2000, 4000)

            # Step 6: Check for 2FA or security challenge
            current_url = page.url.lower()
            if "challenge" in current_url or "verify" in current_url or "mfa" in current_url:
                log.info("2FA/MFA challenge detected, waiting for user")
                await self._wait_for_user(
                    page,
                    "Complete 2FA verification in the browser window",
                    f'a[href*="{NELNET_BASE_URL}"], [data-testid="dashboard"]',
                    timeout=120_000,
                )

            # Check for login errors
            error_el = await page.query_selector(
                ".validation-summary-errors, .error-message, .field-validation-error"
            )
            if error_el:
                error_text = await error_el.inner_text()
                raise AuthenticationError(
                    f"Login failed: {error_text.strip()}",
                    self.provider_name,
                )

            # Wait for redirect back to main site after auth
            with contextlib.suppress(Exception):
                await page.wait_for_url(
                    f"**{NELNET_BASE_URL}/**", timeout=30_000
                )

            # Ensure we're on the main site dashboard
            if NELNET_AUTH_DOMAIN in page.url or "/account/login" in page.url.lower():
                await page.goto(NELNET_BASE_URL, wait_until="load")
                await self._random_delay(1000, 2000)

            # Verify we're authenticated
            if self._needs_login(page):
                raise AuthenticationError(
                    "Login appeared to succeed but session was not established",
                    self.provider_name,
                )

        except AuthenticationError:
            raise
        except Exception as e:
            if "timeout" in str(e).lower():
                raise ProviderError(
                    "Login timed out. The browser window may need manual interaction.",
                    self.provider_name,
                    detail={"type": "timeout", "page": page.url},
                ) from e
            raise ProviderError(
                f"Login failed: {e}",
                self.provider_name,
            ) from e

    async def _scrape_accounts(self, page: Page) -> list[NelnetAccountData]:
        """Scrape account data from the dashboard.

        NOTE: Selectors below are best-guesses — the real dashboard DOM
        could not be verified without logging in. These use broad fallback
        selectors to improve resilience.
        """
        accounts: list[NelnetAccountData] = []
        try:
            # Ensure we're on the main site dashboard (not login or auth page)
            if self._needs_login(page) or NELNET_AUTH_DOMAIN in page.url:
                await page.goto(NELNET_BASE_URL, wait_until="load")
            await self._random_delay(1000, 2000)

            # Look for loan group sections (unverified selectors)
            loan_sections = await page.query_selector_all(
                ".loan-group, .account-summary, [data-loan-group]"
            )

            if not loan_sections:
                # Fallback: try to get overall balance
                balance_el = await page.query_selector(
                    ".total-balance, .current-balance, [data-balance]"
                )
                if balance_el:
                    balance_text = await balance_el.inner_text()
                    accounts.append(NelnetAccountData(
                        name="Nelnet Student Loan",
                        balance=balance_text.strip(),
                    ))
                return accounts

            for section in loan_sections:
                name_el = await section.query_selector(
                    ".loan-name, .group-name, h3, h4"
                )
                balance_el = await section.query_selector(
                    ".balance, .amount, [data-balance]"
                )
                rate_el = await section.query_selector(
                    ".interest-rate, [data-rate]"
                )
                status_el = await section.query_selector(
                    ".loan-status, [data-status]"
                )

                name = (await name_el.inner_text()).strip() if name_el else "Student Loan"
                balance = (await balance_el.inner_text()).strip() if balance_el else "$0.00"
                rate = (await rate_el.inner_text()).strip() if rate_el else None
                status = (await status_el.inner_text()).strip() if status_el else None

                accounts.append(NelnetAccountData(
                    name=name,
                    balance=balance,
                    interest_rate=rate,
                    status=status,
                ))

        except Exception as e:
            raise ProviderError(
                f"Failed to scrape accounts: {e}",
                self.provider_name,
                detail={"type": "scrape_error", "page": "dashboard"},
            ) from e

        return accounts

    async def _scrape_payments(self, page: Page) -> list[NelnetPaymentData]:
        """Scrape payment history.

        NOTE: Payment page URL and table selectors are best-guesses —
        the real page could not be verified without logging in. Navigates
        via link discovery rather than hardcoded URL.
        """
        payments: list[NelnetPaymentData] = []
        try:
            # Try to find a payment history link on the current page
            # rather than using a hardcoded URL (unverified selectors)
            payment_link = await page.query_selector(
                'a[href*="payment" i], a[href*="billing" i], '
                'a:has-text("Payment History"), a:has-text("Billing")'
            )
            if payment_link:
                await payment_link.click()
                await page.wait_for_load_state("load")
            else:
                # Fallback: try a likely URL path
                await page.goto(
                    f"{NELNET_BASE_URL}/billing/paymenthistory",
                    wait_until="load",
                )
            await self._random_delay(1000, 2000)

            # Unverified selectors — broad fallbacks
            rows = await page.query_selector_all(
                "table tbody tr, .payment-row, [data-payment]"
            )

            for row in rows:
                cells = await row.query_selector_all("td")
                if len(cells) < 3:
                    continue

                date_text = (await cells[0].inner_text()).strip()
                desc_text = (await cells[1].inner_text()).strip()
                amount_text = (await cells[2].inner_text()).strip()
                principal_text = (
                    (await cells[3].inner_text()).strip() if len(cells) > 3 else None
                )
                interest_text = (
                    (await cells[4].inner_text()).strip() if len(cells) > 4 else None
                )

                payments.append(NelnetPaymentData(
                    date=date_text,
                    description=desc_text,
                    amount=amount_text,
                    principal=principal_text,
                    interest=interest_text,
                ))

        except Exception as e:
            raise ProviderError(
                f"Failed to scrape payments: {e}",
                self.provider_name,
                detail={"type": "scrape_error", "page": "payments"},
            ) from e

        return payments


def _parse_currency(text: str) -> int:
    """Parse a currency string like '$1,234.56' to cents (negative for payments)."""
    cleaned = text.replace("$", "").replace(",", "").replace(" ", "").strip()
    if not cleaned or cleaned == "--":
        return 0
    negative = cleaned.startswith(("-", "("))
    cleaned = cleaned.strip("()-")
    try:
        from decimal import ROUND_HALF_UP, Decimal

        cents = int((Decimal(cleaned) * 100).to_integral_value(rounding=ROUND_HALF_UP))
        return -cents if negative else cents
    except Exception:
        return 0


def _parse_date(date_str: str) -> int:
    """Parse MM/DD/YYYY to Unix timestamp."""
    import calendar
    from datetime import datetime

    try:
        dt = datetime.strptime(date_str.strip(), "%m/%d/%Y")
        return int(calendar.timegm(dt.timetuple()))
    except ValueError:
        return int(time.time())


def _stable_id(provider: str, *parts: str) -> str:
    """Generate a stable ID from provider name and identifying parts."""
    raw = ":".join([provider, *parts])
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _to_provider_accounts(
    scraped: list[NelnetAccountData],
) -> list[ProviderAccount]:
    """Transform scraped account data to ProviderAccount."""
    return [
        ProviderAccount(
            id=_stable_id("nelnet", "account", a.name),
            name=a.name,
            currency="USD",
            balance_current=_parse_currency(a.balance),
            account_type="loan/student",
        )
        for a in scraped
    ]


def _to_provider_transactions(
    scraped: list[NelnetPaymentData],
) -> list[ProviderTransaction]:
    """Transform scraped payment data to ProviderTransaction.

    Payments are negative (money going out to pay the loan).
    """
    result: list[ProviderTransaction] = []
    for p in scraped:
        amount = _parse_currency(p.amount)
        # Loan payments are expenses (money out)
        if amount > 0:
            amount = -amount

        tx_date = _parse_date(p.date)
        tx_id = _stable_id("nelnet", "payment", p.date, p.amount, p.description)

        # Build the first account ID to link to
        account_id = _stable_id("nelnet", "account", "Nelnet Student Loan")

        result.append(ProviderTransaction(
            id=tx_id,
            account_id=account_id,
            amount=amount,
            date=tx_date,
            description=p.description or f"Nelnet Payment {p.date}",
            pending=False,
            extra={
                k: v
                for k, v in {
                    "principal": p.principal,
                    "interest": p.interest,
                }.items()
                if v is not None
            } or None,
        ))

    return result
