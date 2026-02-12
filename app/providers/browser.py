"""Browser-based provider base class.

Uses Playwright + stealth for providers that require browser scraping.
Handles session persistence (cookies/localStorage) to avoid repeated 2FA.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.config import settings
from app.providers.base import FinanceProvider, ProviderError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable

    from playwright.async_api import BrowserContext, Page

log = logging.getLogger(__name__)


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
            headless: Override headless mode. Default: settings.browser_headless.

        Yields:
            (page, context) tuple.
        """
        try:
            from playwright.async_api import async_playwright
            from playwright_stealth import Stealth
        except ImportError:
            raise ProviderError(
                "Playwright not installed. Run: pip install playwright playwright-stealth && playwright install chromium",
                self.provider_name,
            ) from None

        if headless is None:
            headless = settings.browser_headless

        pw = await async_playwright().start()
        try:
            launch_args: dict = {
                "headless": headless,
                "args": ["--disable-blink-features=AutomationControlled"],
            }
            if settings.browser_channel:
                launch_args["channel"] = settings.browser_channel
            browser = await pw.chromium.launch(**launch_args)
            try:
                ctx_args: dict = {
                    "viewport": {
                        "width": settings.browser_viewport_width,
                        "height": settings.browser_viewport_height,
                    },
                }
                if session_data:
                    ctx_args["storage_state"] = session_data
                context = await browser.new_context(**ctx_args)
                page = await context.new_page()
                stealth = Stealth()
                await stealth.apply_stealth_async(page)
                page.set_default_timeout(settings.browser_operation_timeout_ms)
                yield page, context
            finally:
                await browser.close()
        finally:
            await pw.stop()

    async def _expect_popup(
        self,
        page: Page,
        trigger_action: Callable[[], Awaitable[None]],
    ) -> Page:
        """Execute trigger_action and return the popup page.

        Useful for OAuth flows that open a new tab/popup for authentication.

        Args:
            page: The current page whose context will spawn the popup.
            trigger_action: Async callable that triggers the popup (e.g. clicking a button).

        Returns:
            The popup Page object, after it has finished loading.
        """
        async with page.context.expect_page() as popup_info:
            await trigger_action()
        popup = await popup_info.value
        await popup.wait_for_load_state("load")
        return popup

    async def _random_delay(self, min_ms: int = 500, max_ms: int = 2000) -> None:
        """Human-like pause between actions."""
        await asyncio.sleep(random.randint(min_ms, max_ms) / 1000)

    async def _type_like_human(
        self, page: Page, selector: str, text: str
    ) -> None:
        """Type text with random delays between keystrokes."""
        await page.click(selector)
        for char in text:
            await page.keyboard.type(
                char,
                delay=random.randint(
                    settings.browser_keystroke_delay_min_ms,
                    settings.browser_keystroke_delay_max_ms,
                ),
            )

    async def _capture_debug_snapshot(self, page: Page, context: str) -> dict:
        """Capture page diagnostics for debugging scrape failures.

        Saves a screenshot to data/debug/ and returns URL, title, and content snippet.
        """
        debug_info: dict = {"url": page.url}
        try:
            debug_info["title"] = await page.title()
        except Exception:
            debug_info["title"] = "<unknown>"

        try:
            body_text = await page.inner_text("body", timeout=3000)
            debug_info["content_snippet"] = body_text[:2000]
        except Exception:
            debug_info["content_snippet"] = "<could not extract>"

        try:
            debug_dir = Path("data/debug")
            debug_dir.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            filename = f"{self.provider_name}_{context}_{ts}.png"
            screenshot_path = debug_dir / filename
            await page.screenshot(path=str(screenshot_path), full_page=True)
            debug_info["screenshot_path"] = str(screenshot_path)
            log.info("Debug screenshot saved: %s", screenshot_path)
        except Exception as e:
            log.warning("Failed to save debug screenshot: %s", e)
            debug_info["screenshot_path"] = None

        log.error(
            "Scrape failure [%s]: url=%s title=%s content=%.200s",
            context,
            debug_info["url"],
            debug_info["title"],
            debug_info.get("content_snippet", "")[:200],
        )
        return debug_info

    async def _wait_for_user(
        self,
        page: Page,
        prompt: str,
        check_selector: str,
        timeout: int = 120_000,
    ) -> None:
        """Wait for user to complete an action (e.g. 2FA) in the headed browser."""
        log.info("Waiting for user action: %s", prompt)
        await page.wait_for_selector(check_selector, timeout=timeout)
