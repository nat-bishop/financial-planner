"""Nelnet student loan provider — browser-based scraping.

Two layers for testability:
1. Scraper methods (_login, _scrape_*) — interact with Playwright
2. Data transformation (_to_provider_*) — pure functions, tested with fixtures

Selectors verified against real site on 2026-02-11 via Playwright inspection.
"""

from __future__ import annotations

import calendar
import contextlib
import hashlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from app.providers.base import AuthenticationError, ProviderError, TwoFAHandler
from app.providers.browser import BrowserProvider
from app.providers.models import ProviderAccount, ProviderTransaction, SyncResult
from app.services.two_fa import TWO_FA_MAX_ATTEMPTS, TwoFAChallenge

if TYPE_CHECKING:
    from playwright.async_api import Page

log = logging.getLogger(__name__)

NELNET_BASE_URL = "https://nelnet.studentaid.gov"
NELNET_LOGIN_URL = f"{NELNET_BASE_URL}/account/login"
NELNET_AUTH_DOMAIN = "auth.nelnet.studentaid.gov"
NELNET_LOAN_DETAILS_URL = f"{NELNET_BASE_URL}/loan-details"
NELNET_PAYMENT_ACTIVITY_URL = f"{NELNET_BASE_URL}/payments/payment-activity"


@dataclass
class NelnetAccountData:
    """Raw scraped loan group data from /loan-details."""

    group_name: str  # e.g., "Group: AA"
    loan_type: str  # e.g., "DIRECT SUB", "DIRECT UNSUB", "DIRECT GRAD"
    status: str  # e.g., "REPAYMENT", "Paid In Full"
    outstanding_balance: str  # e.g., "$3,490.45"
    interest_rate: str | None = None  # e.g., "3.510%"


@dataclass
class NelnetPaymentData:
    """Raw scraped payment row from /payments/payment-activity."""

    date: str  # e.g., "01/28/2026"
    amount: str  # e.g., "$266.83"
    principal: str  # e.g., "$248.66"
    interest: str  # e.g., "$18.17"
    payment_type: str  # e.g., "Auto Debit", "Electronic", "Other"


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
        two_fa_handler: TwoFAHandler | None = None,
    ) -> SyncResult:
        try:
            return await self._do_sync(credential_data, cursor, session_data, two_fa_handler)
        except ProviderError:
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
        two_fa_handler: TwoFAHandler | None = None,
    ) -> SyncResult:
        async with self._browser_session(session_data) as (page, context):
            # Navigate to dashboard — if session is valid, we stay there.
            # If not, the site redirects us to the login page.
            await page.goto(f"{NELNET_BASE_URL}/dashboard", wait_until="load")
            with contextlib.suppress(Exception):
                await page.wait_for_load_state("networkidle", timeout=15_000)
            await self._random_delay(1000, 2000)

            if self._needs_login(page):
                log.info("Session expired or first login, authenticating")
                await page.goto(NELNET_LOGIN_URL, wait_until="load")
                await self._random_delay(1000, 2000)
                await self._login(page, credential_data, two_fa_handler)
            else:
                log.info("Session valid, skipping login")

            # Dismiss "View Your Statements" dialog if present
            await self._dismiss_dialog(page)

            raw_accounts = await self._scrape_accounts(page)
            raw_payments = await self._scrape_payments(page)

            session = await context.storage_state()

            return SyncResult(
                accounts=_to_provider_accounts(raw_accounts),
                transactions=_to_provider_transactions(raw_accounts, raw_payments),
                session_data=session,
            )

    def _needs_login(self, page: Page) -> bool:
        """Check if on a login or auth page (not the dashboard).

        Checks the URL host only — not query params, which can contain
        auth domain references (e.g. ``iss=...auth.nelnet.studentaid.gov``).
        """
        from urllib.parse import urlparse

        parsed = urlparse(page.url)
        host = parsed.hostname or ""
        path = parsed.path.lower()
        return (
            host == NELNET_AUTH_DOMAIN
            or "/account/login" in path
        )

    async def _dismiss_dialog(self, page: Page) -> None:
        """Close the 'View Your Statements' popup if it appears after login."""
        with contextlib.suppress(Exception):
            close_btn = page.get_by_role("button", name="Close button")
            await close_btn.click(timeout=3000)

    async def _login(
        self, page: Page, creds: dict, two_fa_handler: TwoFAHandler | None = None
    ) -> None:
        """Nelnet login flow with exact selectors (verified 2026-02-11).

        Steps:
        1. Click "Continue" on borrower selection page
        2. Accept federal usage disclaimer dialog
        3. Fill username + password on auth page
        4. Click "Continue" to submit
        5. Handle 2FA if redirected to /MFA/AuthChoice
        """
        try:
            # Step 1: Click Continue (borrower radio is pre-selected)
            continue_btn = page.get_by_role("button", name="Continue")
            await continue_btn.wait_for(timeout=30_000)
            await continue_btn.click()
            await self._random_delay(500, 1000)

            # Step 2: Remove Transcend consent overlay (blocks clicks), then accept disclaimer
            await page.evaluate("""() => {
                const el = document.getElementById('transcend-consent-manager');
                if (el) el.remove();
            }""")
            accept_btn = page.get_by_role("button", name="accept federal usage disclaimer")
            await accept_btn.wait_for(timeout=15_000)
            await accept_btn.click()

            # Step 3: Wait for redirect to auth page, fill credentials
            await page.wait_for_url(f"**{NELNET_AUTH_DOMAIN}/**", timeout=30_000)
            await page.wait_for_load_state("load")
            await self._random_delay(500, 1000)

            username_field = page.get_by_role("textbox", name="Username")
            await username_field.wait_for(timeout=15_000)
            await username_field.fill(creds["username"])

            password_field = page.get_by_role("textbox", name="Password")
            await password_field.fill(creds["password"])
            await self._random_delay(300, 700)

            # Step 4: Submit login
            await page.get_by_role("button", name="Continue").click()
            await self._random_delay(2000, 4000)

            # Step 5: Check where we ended up
            if "/MFA/" in page.url:
                log.info("2FA required at %s", page.url)
                await self._handle_2fa(page, two_fa_handler)

            # Wait for redirect to main site
            with contextlib.suppress(Exception):
                await page.wait_for_url(f"**{NELNET_BASE_URL}/**", timeout=30_000)

            # Verify authentication succeeded
            if self._needs_login(page):
                raise AuthenticationError(
                    "Login failed — still on auth page after submission",
                    self.provider_name,
                )

        except ProviderError:
            raise
        except Exception as e:
            if "timeout" in str(e).lower():
                raise ProviderError(
                    "Login timed out",
                    self.provider_name,
                    detail={"type": "timeout", "page": page.url},
                ) from e
            raise ProviderError(
                f"Login failed: {e}",
                self.provider_name,
            ) from e

    async def _handle_2fa(
        self, page: Page, two_fa_handler: TwoFAHandler | None
    ) -> None:
        """Handle Nelnet's email-based 2FA (exact selectors from /MFA/AuthChoice and /MFA/Verify)."""
        if two_fa_handler is None:
            log.info("No 2FA handler — waiting for manual completion in headed browser")
            await page.wait_for_url(f"**{NELNET_BASE_URL}/**", timeout=120_000)
            return

        # AuthChoice page: email radio is already selected by default, click Send Code
        if "/MFA/AuthChoice" in page.url:
            await page.get_by_role("button", name="Send Code").click()
            await self._random_delay(1000, 2000)

        # Now on /MFA/Verify — read the prompt text
        prompt_text = "Enter the verification code sent to your email"
        with contextlib.suppress(Exception):
            prompt_el = page.locator("p").filter(has_text="We've sent a one-time use code to")
            text = await prompt_el.inner_text(timeout=5000)
            if text:
                prompt_text = text.strip()

        challenge = TwoFAChallenge(
            method="email",
            prompt=prompt_text,
            methods_available=["email"],
        )

        for attempt in range(TWO_FA_MAX_ATTEMPTS):
            if attempt > 0:
                challenge = TwoFAChallenge(
                    method="email",
                    prompt=f"Code was incorrect. {prompt_text} (attempt {attempt + 1}/{TWO_FA_MAX_ATTEMPTS})",
                    methods_available=["email"],
                )

            code = await two_fa_handler(challenge)

            await page.get_by_role("textbox", name="Authentication Code").fill(code)
            await page.get_by_role("checkbox", name="Remember this device for 90 days.").check()
            await self._random_delay(300, 600)
            await page.get_by_role("button", name="Verify").click()

            # Wait for redirect chain: /MFA/Verify → auth callback → main site
            try:
                await page.wait_for_url(
                    f"**{NELNET_BASE_URL}/**", timeout=30_000
                )
                # Let the redirect chain settle (callback → dashboard)
                await page.wait_for_load_state("networkidle", timeout=15_000)
                log.info("2FA verification successful, redirected to %s", page.url)
                return
            except Exception:
                pass

            # If still on MFA page, code was likely rejected
            if "/MFA/" in page.url:
                log.warning("2FA code rejected (attempt %d/%d)", attempt + 1, TWO_FA_MAX_ATTEMPTS)
                continue

            # Left MFA but redirect didn't fully complete — give more time
            with contextlib.suppress(Exception):
                await page.wait_for_load_state("networkidle", timeout=15_000)
            log.info("2FA complete, current URL: %s", page.url)
            return

        raise ProviderError(
            f"2FA failed after {TWO_FA_MAX_ATTEMPTS} attempts",
            self.provider_name,
        )

    async def _scrape_accounts(self, page: Page) -> list[NelnetAccountData]:
        """Scrape loan groups from /loan-details (verified selectors 2026-02-11).

        Each loan group has a heading "Group: XX" followed by structured key-value pairs.
        """
        accounts: list[NelnetAccountData] = []
        try:
            await page.goto(NELNET_LOAN_DETAILS_URL, wait_until="load")
            await self._random_delay(1000, 2000)

            # Wait for the page to be ready
            await page.get_by_text("Group and Loan Summary").wait_for(timeout=15_000)

            # Find all group sections by their headings
            group_headings = await page.get_by_role("heading", level=2).all()

            for heading in group_headings:
                text = await heading.inner_text()
                if not text.startswith("Group:"):
                    continue

                group_name = text.strip()

                # The group's data container is the next sibling of the heading
                section = heading.locator("..")  # parent container

                # Extract key-value pairs from the section
                loan_type = await self._extract_field(section, "Loan Type:")
                status = await self._extract_field(section, "Status:")
                outstanding_balance = await self._extract_field(section, "Outstanding Balance:")
                interest_rate = await self._extract_field(section, "Effective Interest Rate:")

                if not loan_type or not status:
                    continue

                # Skip paid-off loans
                if status == "Paid In Full":
                    continue

                accounts.append(NelnetAccountData(
                    group_name=group_name,
                    loan_type=loan_type,
                    status=status,
                    outstanding_balance=outstanding_balance or "$0.00",
                    interest_rate=interest_rate,
                ))

        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(
                f"Failed to scrape accounts: {e}",
                self.provider_name,
                detail={"type": "scrape_error", "page": "loan-details"},
            ) from e

        return accounts

    async def _extract_field(self, section, label: str) -> str | None:
        """Extract the value text following a label within a section.

        On the loan details page, fields are structured as sibling elements:
            <div>Loan Type:</div>
            <div>DIRECT SUB</div>
        """
        try:
            label_el = section.locator(f"text='{label}'").first
            # The value is the next sibling element
            value_el = label_el.locator("xpath=following-sibling::*[1]")
            text = await value_el.inner_text(timeout=3000)
            return text.strip() if text else None
        except Exception:
            return None

    async def _scrape_payments(self, page: Page) -> list[NelnetPaymentData]:
        """Scrape payment history from /payments/payment-activity (verified selectors 2026-02-11).

        The page has an HTML table with columns:
        Payment Date | Payment Amount | Applied to Principal | Applied to Interest | Payment Type
        """
        payments: list[NelnetPaymentData] = []
        try:
            await page.goto(NELNET_PAYMENT_ACTIVITY_URL, wait_until="load")
            await self._random_delay(1000, 2000)

            # Wait for table to appear
            table = page.get_by_role("table", name="Payment History")
            await table.wait_for(timeout=15_000)

            # Select "All" to get full history (default is "Last 12 Months")
            show_combo = page.get_by_role("combobox", name="Show")
            await show_combo.select_option("All")
            await self._random_delay(1000, 2000)

            # Read all pages of results
            while True:
                payments.extend(await self._read_payment_rows(page))

                # Check for next page
                next_btn = page.get_by_role("button", name="Next Page")
                if await next_btn.is_disabled():
                    break
                await next_btn.click()
                await self._random_delay(1000, 2000)

        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(
                f"Failed to scrape payments: {e}",
                self.provider_name,
                detail={"type": "scrape_error", "page": "payment-activity"},
            ) from e

        return payments

    async def _read_payment_rows(self, page: Page) -> list[NelnetPaymentData]:
        """Read payment rows from the currently visible table page."""
        payments: list[NelnetPaymentData] = []

        table = page.get_by_role("table", name="Payment History")
        rows = await table.get_by_role("row").all()

        for row in rows:
            cells = await row.get_by_role("cell").all()
            if len(cells) < 5:
                continue  # Skip header rows (they use columnheader, not cell)

            date_text = (await cells[0].inner_text()).strip()
            amount_text = (await cells[1].inner_text()).strip()
            principal_text = (await cells[2].inner_text()).strip()
            interest_text = (await cells[3].inner_text()).strip()
            # Payment type cell contains a "Posted" icon + type text
            type_text = (await cells[4].inner_text()).strip()
            # Clean up: remove "Posted" prefix that comes from the status icon alt text
            type_text = re.sub(r"^Posted\s*", "", type_text).strip()

            payments.append(NelnetPaymentData(
                date=date_text,
                amount=amount_text,
                principal=principal_text,
                interest=interest_text,
                payment_type=type_text or "Payment",
            ))

        return payments


def _parse_currency(text: str) -> int:
    """Parse a currency string like '$1,234.56' to cents (negative for payments)."""
    cleaned = text.replace("$", "").replace(",", "").replace(" ", "").strip()
    if not cleaned or cleaned == "--":
        return 0
    negative = cleaned.startswith(("-", "("))
    cleaned = cleaned.strip("()-")
    try:
        cents = int((Decimal(cleaned) * 100).to_integral_value(rounding=ROUND_HALF_UP))
        return -cents if negative else cents
    except Exception:
        return 0


def _parse_date(date_str: str) -> int:
    """Parse MM/DD/YYYY to Unix timestamp."""
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
    """Transform scraped loan group data to ProviderAccount list."""
    return [
        ProviderAccount(
            id=_stable_id("nelnet", "account", a.group_name),
            name=f"Nelnet {a.group_name} - {a.loan_type}",
            currency="USD",
            balance_current=_parse_currency(a.outstanding_balance),
            account_type="loan/student",
        )
        for a in scraped
    ]


def _to_provider_transactions(
    accounts: list[NelnetAccountData],
    scraped: list[NelnetPaymentData],
) -> list[ProviderTransaction]:
    """Transform scraped payment data to ProviderTransaction.

    Payments are negative (money going out to pay the loan).
    Links transactions to the first active account.
    """
    # Use the first account as the default linkage
    if accounts:
        default_account_id = _stable_id("nelnet", "account", accounts[0].group_name)
    else:
        default_account_id = _stable_id("nelnet", "account", "Nelnet Student Loan")

    result: list[ProviderTransaction] = []
    for p in scraped:
        amount = _parse_currency(p.amount)
        # Loan payments are expenses (money out)
        if amount > 0:
            amount = -amount

        tx_date = _parse_date(p.date)
        tx_id = _stable_id("nelnet", "payment", p.date, p.amount, p.payment_type)

        result.append(ProviderTransaction(
            id=tx_id,
            account_id=default_account_id,
            amount=amount,
            date=tx_date,
            description=f"Nelnet {p.payment_type} Payment",
            pending=False,
            extra={
                "principal": p.principal,
                "interest": p.interest,
                "payment_type": p.payment_type,
            },
        ))

    return result
