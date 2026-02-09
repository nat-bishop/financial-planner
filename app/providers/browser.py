"""Browser-based provider base class.

Uses Playwright + stealth for providers that require browser scraping.
Handles session persistence (cookies/localStorage) to avoid repeated 2FA.
"""

from __future__ import annotations

import asyncio
import os
import random
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from app.providers.base import FinanceProvider, ProviderError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from playwright.async_api import BrowserContext, Page

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


class BrowserProvider(FinanceProvider):
    """Base class for browser-based providers.

    Subclasses implement validate_credentials() and sync().
    This class provides session management and anti-detection utilities.
    """

    @asynccontextmanager
    async def _browser_session(
        self,
        session_data: dict | None = None,
        headless: bool | None = None,
    ) -> AsyncGenerator[tuple[Page, BrowserContext], None]:
        """Launch Playwright browser with stealth, optionally restoring session.

        Args:
            session_data: Playwright storageState dict to restore.
            headless: Override headless mode. Default: BROWSER_HEADLESS env var.

        Yields:
            (page, context) tuple.
        """
        try:
            from playwright.async_api import async_playwright
            from playwright_stealth import stealth_async
        except ImportError as e:
            raise ProviderError(
                "Playwright not installed. Run: pip install playwright playwright-stealth && playwright install chromium",
                self.provider_name,
            ) from e

        if headless is None:
            headless = os.environ.get("BROWSER_HEADLESS", "").lower() in ("1", "true")

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            ctx_args: dict = {
                "viewport": {"width": 1280, "height": 800},
                "user_agent": _USER_AGENT,
            }
            if session_data:
                ctx_args["storage_state"] = session_data
            context = await browser.new_context(**ctx_args)
            page = await context.new_page()
            await stealth_async(page)
            page.set_default_timeout(30_000)  # 30s per-operation timeout
            yield page, context
        finally:
            await browser.close()
            await pw.stop()

    async def _random_delay(self, min_ms: int = 500, max_ms: int = 2000) -> None:
        """Human-like pause between actions."""
        await asyncio.sleep(random.randint(min_ms, max_ms) / 1000)

    async def _type_like_human(
        self, page: Page, selector: str, text: str
    ) -> None:
        """Type text with random delays between keystrokes."""
        await page.click(selector)
        for char in text:
            await page.keyboard.type(char, delay=random.randint(50, 150))

    async def _wait_for_user(
        self,
        page: Page,
        prompt: str,
        check_selector: str,
        timeout: int = 120_000,
    ) -> None:
        """Wait for user to complete an action (e.g. 2FA) in the headed browser.

        Args:
            page: Playwright page.
            prompt: Description of what the user should do (logged).
            check_selector: CSS selector that appears when action is complete.
            timeout: Max wait time in ms.
        """
        import logging

        log = logging.getLogger(__name__)
        log.info("Waiting for user action: %s", prompt)
        await page.wait_for_selector(check_selector, timeout=timeout)
