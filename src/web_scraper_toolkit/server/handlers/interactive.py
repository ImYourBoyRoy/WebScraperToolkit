# ./src/web_scraper_toolkit/server/handlers/interactive.py
"""
Interactive Browser Session Handler
=====================================

Manages a persistent headed Playwright browser session for AI-driven
interactive browsing. The session persists across MCP tool calls so an
AI agent can navigate, click, type, wait, scroll, hover, inspect element maps,
read content, and solve challenges across
multiple round-trips.

Run: Imported by server.mcp_tools.browser_interactive; not standalone.
Inputs: URLs, CSS selectors, text, JS expressions, and interaction controls from MCP tool calls.
Outputs: Page state dicts (url, title, html, screenshot bytes).
Side effects: Opens a real browser window, performs network activity.
Notes:
  - Session is created lazily on first navigate call.
  - Challenge solvers (CF + PX) run automatically on every navigation.
  - LLM control helpers are context-capped for predictable token usage.
  - Session is torn down by explicit close or server shutdown.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import shutil
import tempfile
from typing import Any, Dict, List, Optional

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from ...browser.playwright_handler import _PX_CHALLENGE_MARKERS
from ._interactive import (
    run_accessibility_tree,
    run_hover,
    run_interaction_map,
    run_press_key,
    run_scroll,
    run_wait_for,
)
from .config import get_browser_config

logger = logging.getLogger("mcp_server.interactive")

# ---------------------------------------------------------------------------
# Stealth helpers (lazy imports)
# ---------------------------------------------------------------------------

try:
    from playwright_stealth import Stealth as _StealthClass
except ImportError:
    _StealthClass = None


# ---------------------------------------------------------------------------
# Singleton interactive session
# ---------------------------------------------------------------------------


class InteractiveSession:
    """
    Persistent browser session for AI-interactive browsing.

    Lifecycle:
      1. Created lazily on first `navigate()` call.
      2. Reused across all subsequent calls.
      3. Destroyed by `close()` or server shutdown.
    """

    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._stealth: Any = _StealthClass() if _StealthClass else None
        self._lock = asyncio.Lock()
        self._temp_profile_dir: Optional[str] = None

    @property
    def is_active(self) -> bool:
        return self._page is not None

    async def _ensure_browser(self) -> Page:
        """Spin up browser + context + page if not already running."""
        if self._page is not None:
            return self._page

        async with self._lock:
            if self._page is not None:
                return self._page

            browser_cfg = get_browser_config()
            interactive_channel = (
                str(getattr(browser_cfg, "interactive_channel", "chrome") or "chrome")
                .strip()
                .lower()
            )
            if interactive_channel not in {"chrome", "msedge", "chromium"}:
                interactive_channel = "chrome"

            context_mode = (
                str(
                    getattr(browser_cfg, "interactive_context_mode", "incognito")
                    or "incognito"
                )
                .strip()
                .lower()
            )
            if context_mode not in {"incognito", "persistent"}:
                context_mode = "incognito"

            logger.info(
                "InteractiveSession: Starting browser channel=%s context_mode=%s",
                interactive_channel,
                context_mode,
            )

            pw = await async_playwright().__aenter__()
            self._playwright = pw

            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
            launch_kwargs: Dict[str, Any] = {
                "headless": False,
                "args": launch_args,
                "ignore_default_args": ["--enable-automation"],
            }
            if interactive_channel != "chromium":
                launch_kwargs["channel"] = interactive_channel

            viewport = {"width": 1366, "height": 768}
            clean_ua = ""
            major = "131"
            self._temp_profile_dir = None

            if context_mode == "persistent":
                profile_dir = str(
                    getattr(browser_cfg, "interactive_profile_dir", "") or ""
                ).strip()
                if not profile_dir:
                    profile_dir = tempfile.mkdtemp(prefix="wst_interactive_profile_")
                    self._temp_profile_dir = profile_dir
                context = await pw.chromium.launch_persistent_context(
                    user_data_dir=profile_dir,
                    viewport=viewport,
                    screen=viewport,
                    locale="en-US",
                    timezone_id="America/Denver",
                    java_script_enabled=True,
                    ignore_https_errors=True,
                    **launch_kwargs,
                )
                browser = context.browser
                page = context.pages[0] if context.pages else await context.new_page()
                native_ua = ""
                try:
                    native_ua = await page.evaluate("navigator.userAgent")
                except Exception:
                    native_ua = ""
                clean_ua = native_ua.replace("HeadlessChrome", "Chrome")
                match = re.search(r"Chrome/(\d+)\.", clean_ua)
                major = match.group(1) if match else "131"
                await context.set_extra_http_headers(
                    {
                        "Sec-Ch-Ua": f'"Google Chrome";v="{major}", "Not=A?Brand";v="8", "Chromium";v="{major}"',
                        "Sec-Ch-Ua-Mobile": "?0",
                        "Sec-Ch-Ua-Platform": '"Windows"',
                        "Accept-Language": "en-US,en;q=0.9",
                    }
                )
            else:
                browser = await pw.chromium.launch(**launch_kwargs)
                dummy_ctx = await browser.new_context()
                dummy_page = await dummy_ctx.new_page()
                native_ua = await dummy_page.evaluate("navigator.userAgent")
                await dummy_ctx.close()

                clean_ua = native_ua.replace("HeadlessChrome", "Chrome")
                match = re.search(r"Chrome/(\d+)\.", clean_ua)
                major = match.group(1) if match else "131"

                context = await browser.new_context(
                    user_agent=clean_ua,
                    viewport=viewport,
                    screen=viewport,
                    extra_http_headers={
                        "Sec-Ch-Ua": f'"Google Chrome";v="{major}", "Not=A?Brand";v="8", "Chromium";v="{major}"',
                        "Sec-Ch-Ua-Mobile": "?0",
                        "Sec-Ch-Ua-Platform": '"Windows"',
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                    locale="en-US",
                    timezone_id="America/Denver",
                    java_script_enabled=True,
                    ignore_https_errors=True,
                )
                page = await context.new_page()

            self._browser = browser
            self._context = context

            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            await context.add_init_script(
                """
                Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
                Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
                Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});
                """
            )

            self._page = page
            logger.info(
                "InteractiveSession: Browser ready channel=%s mode=%s viewport=%dx%d ua_major=%s",
                interactive_channel,
                context_mode,
                viewport["width"],
                viewport["height"],
                major,
            )
            return page

    async def navigate(
        self, url: str, wait_until: str = "domcontentloaded"
    ) -> Dict[str, Any]:
        """Navigate to URL, auto-solve challenges, return page state."""
        page = await self._ensure_browser()

        try:
            response = await page.goto(url, wait_until=wait_until, timeout=30000)
        except Exception as exc:
            logger.warning("InteractiveSession: Navigation error: %s", exc)
            response = None

        # Wait for dynamic challenge iframes (PX loads after initial page)
        # Poll up to ~8 seconds for a challenge to appear, break early if found.
        for _wait_tick in range(8):
            await page.wait_for_timeout(1000)
            try:
                content_check = (await page.content()).lower()
            except Exception:
                break
            if any(m in content_check for m in _PX_CHALLENGE_MARKERS):
                logger.info(
                    "InteractiveSession: PX challenge detected after %ds.",
                    _wait_tick + 1,
                )
                break
            title_check = ""
            try:
                title_check = (await page.title()).lower()
            except Exception:
                pass
            if "just a moment" in title_check or "attention required" in title_check:
                break

        # Auto-solve challenges
        await self._auto_solve_challenges(page)

        return await self._page_state(response)

    async def click(self, selector: str) -> Dict[str, Any]:
        """Click an element by CSS selector."""
        page = await self._ensure_browser()
        await page.click(selector, timeout=10000)
        await page.wait_for_timeout(1000)
        return await self._page_state()

    async def type_text(self, selector: str, text: str) -> Dict[str, Any]:
        """Type text into an input field."""
        page = await self._ensure_browser()
        await page.fill(selector, text, timeout=10000)
        return await self._page_state()

    async def wait_for(
        self,
        selector: Optional[str] = None,
        state: str = "visible",
        timeout_ms: int = 5000,
    ) -> Dict[str, Any]:
        """
        Wait for an element state transition or a fixed delay.

        If `selector` is omitted, this behaves like a timed pause.
        """
        page = await self._ensure_browser()
        wait_data = await run_wait_for(page, selector, state, timeout_ms)
        page_state = await self._page_state()
        page_state["wait"] = wait_data
        return page_state

    async def press_key(
        self,
        key: str,
        selector: Optional[str] = None,
        delay_ms: int = 0,
    ) -> Dict[str, Any]:
        """Press a key, optionally focusing a selector first."""
        page = await self._ensure_browser()
        keyboard_data = await run_press_key(page, key, selector, delay_ms)
        page_state = await self._page_state()
        page_state["keyboard"] = keyboard_data
        return page_state

    async def scroll(
        self,
        direction: str = "down",
        amount: int = 1000,
        selector: Optional[str] = None,
        smooth: bool = True,
    ) -> Dict[str, Any]:
        """Scroll the page (or a scrollable element) in the requested direction."""
        page = await self._ensure_browser()
        scroll_data = await run_scroll(
            page=page,
            direction=direction,
            amount=amount,
            selector=selector,
            smooth=smooth,
        )
        page_state = await self._page_state()
        page_state["scroll"] = scroll_data
        return page_state

    async def hover(self, selector: str) -> Dict[str, Any]:
        """Hover over an element by CSS selector."""
        page = await self._ensure_browser()
        hover_data = await run_hover(page, selector)
        page_state = await self._page_state()
        page_state["hover"] = hover_data
        return page_state

    async def get_interaction_map(
        self,
        selector: Optional[str] = None,
        max_elements: int = 60,
        include_hidden: bool = False,
    ) -> Dict[str, Any]:
        """
        Return a compact, LLM-friendly map of interactive elements.

        Includes short selector hints and bounded element counts to keep
        multi-turn prompts efficient and deterministic.
        """
        page = await self._ensure_browser()
        interaction_map = await run_interaction_map(
            page=page,
            selector=selector,
            max_elements=max_elements,
            include_hidden=include_hidden,
        )
        page_state = await self._page_state()
        page_state["interaction_map"] = interaction_map
        return page_state

    async def get_accessibility_tree(
        self,
        selector: Optional[str] = None,
        interesting_only: bool = True,
        max_nodes: int = 120,
        max_text_length: int = 160,
    ) -> Dict[str, Any]:
        """
        Return a trimmed accessibility tree (Playwright snapshot) for robust LLM navigation.

        This complements selector-based discovery with role/name semantics.
        """
        page = await self._ensure_browser()
        accessibility_tree = await run_accessibility_tree(
            page=page,
            selector=selector,
            interesting_only=interesting_only,
            max_nodes=max_nodes,
            max_text_length=max_text_length,
        )
        page_state = await self._page_state()
        page_state["accessibility_tree"] = accessibility_tree
        return page_state

    async def screenshot(self) -> str:
        """Capture current page screenshot, return base64-encoded PNG."""
        page = await self._ensure_browser()
        data = await page.screenshot(type="png")
        return base64.b64encode(data).decode("ascii")

    async def read_page(
        self,
        selector: Optional[str] = None,
        format: str = "text",
    ) -> Dict[str, Any]:
        """Read page content. Format: text | html | markdown."""
        page = await self._ensure_browser()

        if selector:
            el = page.locator(selector).first
            if format == "html":
                content = await el.evaluate("el => el.outerHTML")
            else:
                content = await el.inner_text()
        else:
            if format == "html":
                content = await page.content()
            else:
                content = await page.inner_text("body")

        state = await self._page_state()
        state["content"] = content
        state["format"] = format
        return state

    async def evaluate(self, expression: str) -> Any:
        """Run a JS expression on the page and return the result."""
        page = await self._ensure_browser()
        return await page.evaluate(expression)

    async def solve_challenges(self) -> Dict[str, Any]:
        """Explicitly trigger all challenge solvers on the current page."""
        page = await self._ensure_browser()
        solved = await self._auto_solve_challenges(page)
        state = await self._page_state()
        state["challenges_solved"] = solved
        return state

    async def get_elements(self, selector: str) -> List[Dict[str, Any]]:
        """Return visible elements matching a selector with text + attributes."""
        page = await self._ensure_browser()
        elements = []
        locator = page.locator(selector)
        count = await locator.count()
        for i in range(min(count, 50)):
            try:
                el = locator.nth(i)
                text = (await el.inner_text()).strip()[:200]
                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                href = await el.get_attribute("href")
                elements.append(
                    {
                        "index": i,
                        "tag": tag,
                        "text": text,
                        "href": href,
                    }
                )
            except Exception:
                continue
        return elements

    async def close(self) -> bool:
        """Tear down the browser session."""
        async with self._lock:
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
            if self._playwright:
                try:
                    await self._playwright.__aexit__(None, None, None)
                except (Exception, OSError, ValueError):
                    # Suppress pipe errors during event loop teardown
                    pass
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
            if self._temp_profile_dir:
                shutil.rmtree(self._temp_profile_dir, ignore_errors=True)
                self._temp_profile_dir = None
            logger.info("InteractiveSession: Closed.")
            return True

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    async def _page_state(self, response: Any = None) -> Dict[str, Any]:
        """Capture current page state as a dict."""
        page = self._page
        if page is None:
            return {"error": "No active session"}

        try:
            title = await page.title()
        except Exception:
            title = ""
        try:
            url = page.url
        except Exception:
            url = ""

        status = response.status if response else None
        return {
            "url": url,
            "title": title,
            "status": status,
        }

    async def _auto_solve_challenges(self, page: Page) -> bool:
        """Run all available challenge solvers on the current page."""
        content = await page.content()
        content_lower = content.lower()

        try:
            title = (await page.title()).lower()
        except Exception:
            title = ""

        solved_any = False

        # 1. Cloudflare "Just a moment" spatial solver
        if (
            "just a moment" in title
            or "attention required" in title
            or ("cloudflare" in content_lower and "challenge" in content_lower)
        ):
            logger.info("InteractiveSession: CF challenge detected, solving...")
            try:
                from ...browser.solver import CloudflareSolver

                if await CloudflareSolver.solve_spatial(page):
                    solved_any = True
                    await page.wait_for_timeout(2000)
            except Exception as exc:
                logger.warning("InteractiveSession: CF solver error: %s", exc)

        # 2. PerimeterX Press & Hold
        if any(marker in content_lower for marker in _PX_CHALLENGE_MARKERS):
            logger.info("InteractiveSession: PX challenge detected, solving...")
            try:
                from ...browser.px_solver import PerimeterXSolver

                if PerimeterXSolver.is_available():
                    cb_ok = await PerimeterXSolver.solve_cloudflare_checkbox(page)
                    if cb_ok:
                        await page.wait_for_timeout(1000)
                    ph_ok = await PerimeterXSolver.solve_press_and_hold(page)
                    if ph_ok:
                        solved_any = True
                        await page.wait_for_timeout(2000)
                else:
                    logger.warning(
                        "InteractiveSession: PX solver unavailable (pyautogui missing)."
                    )
            except Exception as exc:
                logger.warning("InteractiveSession: PX solver error: %s", exc)

        return solved_any


# Module-level singleton
_session = InteractiveSession()


def get_interactive_session() -> InteractiveSession:
    """Return the module-level interactive session singleton."""
    return _session
