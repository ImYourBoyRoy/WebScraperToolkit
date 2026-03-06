# ./src/web_scraper_toolkit/browser/_playwright_handler/page_ops.py
"""
Page/context creation and fetch operations for PlaywrightManager.
Used by composed manager class for baseline request execution and challenge handling.
Run: imported by browser facade class composition.
Inputs: target URLs, page objects, and per-request fetch options.
Outputs: fetched content/URL/status tuples and created page/context handles.
Side effects: network requests, context/page creation, optional solver interaction.
Operational notes: retains legacy micro-interaction and challenge detection behavior.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import random
from typing import Any, Dict, Optional, Tuple, cast
from urllib.parse import urlparse

from playwright.async_api import (
    BrowserContext,
    Page,
    Response as PlaywrightResponse,
    TimeoutError as PlaywrightTimeoutError,
)

from .constants import COMMON_VIEWPORTS, WaitUntilState, _PX_CHALLENGE_MARKERS

try:
    from playwright_stealth import stealth_async as _legacy_stealth_async  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    _legacy_stealth_async = None

logger = logging.getLogger("web_scraper_toolkit.browser.playwright_handler")


class PlaywrightPageOpsMixin:
    async def get_new_page(
        self, context_options: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[Page], Optional[BrowserContext]]:
        """Creates a new page/context."""
        if not self._browser or not self._browser.is_connected():
            logger.warning("Browser not started or not connected. Attempting to start.")
            await self.start()
            if not self._browser or not self._browser.is_connected():
                logger.error("Failed to get new page: Browser could not be started.")
                return None, None

        base_context_options: Dict[str, Any] = {
            "viewport": self.default_viewport,
            "ignore_https_errors": True,
            "java_script_enabled": True,
            "locale": "en-US",
            "timezone_id": "America/New_York",
        }

        if self._experimental_serp:
            viewport = random.choice(COMMON_VIEWPORTS)
            base_context_options["viewport"] = viewport
            base_context_options["screen"] = viewport

        # --- Proxy Injection ---
        if self.proxy_manager:
            try:
                proxy_obj = await self.proxy_manager.get_next_proxy()
                if proxy_obj:
                    protocol = (
                        proxy_obj.protocol.value
                        if hasattr(proxy_obj.protocol, "value")
                        else str(proxy_obj.protocol)
                    )
                    proxy_settings = self._build_playwright_proxy_settings(proxy_obj)

                    base_context_options["proxy"] = proxy_settings
                    logger.info(
                        "Using Proxy: %s (Protocol: %s)",
                        proxy_obj.hostname,
                        protocol,
                    )
            except Exception as e:
                logger.warning(
                    "Failed to get proxy from manager: %s. Proceeding direct.", e
                )

        if context_options:
            base_context_options.update(context_options)

        try:
            context = await self._browser.new_context(**cast(Any, base_context_options))

            # Stealth: Scrub navigator.webdriver (Critical for Cloudflare)
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            if self._experimental_serp:
                await context.add_init_script(
                    """
                    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
                    Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
                    Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});
                    """
                )

                # Consent pre-seeding for experimental SERP profile.
                try:
                    consent_date = datetime.datetime.now(
                        datetime.timezone.utc
                    ).strftime("%Y%m%d")
                    await context.add_cookies(
                        [
                            {
                                "name": "CONSENT",
                                "value": f"YES+cb.{consent_date}-04-p0.en+FX+{random.randint(100, 999)}",
                                "domain": ".google.com",
                                "path": "/",
                            },
                            {
                                "name": "SOCS",
                                "value": "CAISHAgBEhJnd3NfMjAyMzEwMTAtMF9SQzQaAmVuIAEaBgiA_LWoBg",
                                "domain": ".google.com",
                                "path": "/",
                            },
                        ]
                    )
                except Exception:
                    # Non-critical: cookie injection can fail depending on run conditions.
                    pass

            async def _route_handler(route: Any) -> None:
                if self._is_tracker_or_ad(route.request.url):
                    await route.abort()
                    return
                await route.continue_()

            await context.route("**/*", _route_handler)

            page = await context.new_page()
            if self.stealth_mode and self._stealth is not None:
                await self._stealth.apply_stealth_async(page)
            elif self.stealth_mode and callable(_legacy_stealth_async):
                await _legacy_stealth_async(page)
            elif self.stealth_mode and not self._stealth_missing_warned:
                logger.warning(
                    "stealth_mode is enabled but playwright_stealth is unavailable; "
                    "falling back to basic webdriver scrubbing only."
                )
                self._stealth_missing_warned = True
            return page, context
        except Exception as e:
            logger.error("Error creating new page and context: %s", e, exc_info=True)
            return None, None

    def _is_tracker_or_ad(self, url: str) -> bool:
        tracker_domains = [
            "google-analytics.com",
            "googletagmanager.com",
            "scorecardresearch.com",
            "doubleclick.net",
            "adservice.google.com",
            "connect.facebook.net",
            "criteo.com",
            "adsrvr.org",
            "quantserve.com",
            "taboola.com",
            "outbrain.com",
            "hotjar.com",
            "inspectlet.com",
            "optimizely.com",
            "vwo.com",
        ]
        parsed_url = urlparse(url)
        return any(td in parsed_url.netloc for td in tracker_domains)

    async def _perform_micro_interaction(self, page: Page) -> None:
        """Apply tiny user-like interactions for experimental SERP profile only."""
        if not self._experimental_serp:
            return
        try:
            await page.mouse.move(
                random.randint(12, 140),
                random.randint(12, 100),
                steps=random.randint(3, 9),
            )
            await page.wait_for_timeout(random.uniform(120, 260))
        except Exception:
            # Best-effort only.
            return

    async def fetch_page_content(
        self,
        page: Page,
        url: str,
        action_name: str = "fetching page",
        retries: Optional[int] = None,
        navigation_timeout_ms: Optional[int] = None,
        wait_for_selector: Optional[str] = None,
        scroll_to_load: bool = False,
        wait_until_state: WaitUntilState = "domcontentloaded",
        extra_headers: Optional[Dict[str, str]] = None,
        ensure_standard_headers: bool = False,
    ) -> Tuple[Optional[str], str, Optional[int]]:
        """
        Fetches content robustly.
        PATCHED: Removes manual header/UA injection to prevent Cloudflare 'Please Unblock' errors.
        """
        current_url_val = url
        final_url_val = url
        status_code_val: Optional[int] = None

        effective_retries = (
            retries if retries is not None else self.default_action_retries
        )
        effective_nav_timeout = (
            navigation_timeout_ms
            if navigation_timeout_ms is not None
            else self.default_navigation_timeout_ms
        )

        # Header Management:
        # We avoid force-overwriting headers to prevent blocking.
        # Extra headers are applied only if explicitly provided.
        if extra_headers:
            await page.set_extra_http_headers(extra_headers)

        for attempt in range(effective_retries + 1):
            try:
                logger.info(
                    "Playwright: Attempt %s/%s - %s @ %s",
                    attempt + 1,
                    effective_retries + 1,
                    action_name,
                    current_url_val,
                )

                response: Optional[PlaywrightResponse] = await page.goto(
                    current_url_val,
                    timeout=effective_nav_timeout,
                    wait_until=wait_until_state,
                )

                final_url_val = page.url
                if response:
                    status_code_val = response.status

                if status_code_val in [500, 502, 503, 504]:
                    logger.error(
                        "⚠️ SERVER ERROR %s: The target site is down (Gateway/Service Unavailable).",
                        status_code_val,
                    )
                    content = await page.content()
                    return content, final_url_val, status_code_val

                if wait_for_selector:
                    try:
                        await page.wait_for_selector(
                            wait_for_selector,
                            timeout=max(10000, effective_nav_timeout // 2),
                        )
                    except PlaywrightTimeoutError:
                        logger.warning(
                            "Playwright: Selector '%s' not found on %s.",
                            wait_for_selector,
                            final_url_val,
                        )
                else:
                    await page.wait_for_timeout(random.uniform(1500, 3000))

                await self._perform_micro_interaction(page)

                if scroll_to_load:
                    await page.evaluate(
                        "window.scrollTo(0, document.body.scrollHeight)"
                    )
                    await page.wait_for_timeout(1000)

                content = await page.content()
                content_lower = content.lower() if content else ""

                try:
                    current_title = await page.title()
                except Exception:
                    current_title = "Redirecting..."

                if (
                    "just a moment" in current_title.lower()
                    or "attention required" in current_title.lower()
                    or ("cloudflare" in content_lower and "challenge" in content_lower)
                ):
                    logger.info(
                        "Playwright: Cloudflare challenge detected at %s. Engaging Spatial Solver...",
                        final_url_val,
                    )

                    solved = await self._attempt_cloudflare_solve_spatial(page)

                    if solved:
                        logger.info(
                            "Playwright: Spatial Solver reports success. Re-fetching content."
                        )
                        await page.wait_for_timeout(3000)

                        content = await page.content()
                        final_url_val = page.url

                        try:
                            if "just a moment" not in (await page.title()).lower():
                                status_code_val = 200
                        except Exception:
                            pass
                    else:
                        logger.warning(
                            "Playwright: Spatial Solver failed to confirm bypass."
                        )

                # --- PerimeterX Press & Hold / PX-Captcha ---
                content_lower_recheck = content.lower() if content else ""
                if any(
                    marker in content_lower_recheck for marker in _PX_CHALLENGE_MARKERS
                ):
                    logger.info(
                        "Playwright: PerimeterX challenge detected at %s. Engaging PX Solver...",
                        final_url_val,
                    )

                    px_solved = await self._attempt_px_solve(page)

                    if px_solved:
                        logger.info(
                            "Playwright: PX Solver reports success. Re-fetching content."
                        )
                        await page.wait_for_timeout(3000)

                        content = await page.content()
                        final_url_val = page.url

                        try:
                            title_check = (await page.title()).lower()
                            if (
                                "just a moment" not in title_check
                                and "access denied" not in title_check
                            ):
                                status_code_val = 200
                        except Exception:
                            pass
                    else:
                        logger.warning(
                            "Playwright: PX Solver failed to confirm bypass."
                        )

                logger.info(
                    "Playwright: Finished fetch for %s (status: %s, len: %s)",
                    final_url_val,
                    status_code_val,
                    len(content or ""),
                )
                return content, final_url_val, status_code_val

            except PlaywrightTimeoutError as pte:
                logger.warning(
                    "Playwright: Timeout on %s (attempt %s/%s): %s",
                    current_url_val,
                    attempt + 1,
                    effective_retries + 1,
                    pte,
                )
            except asyncio.CancelledError:
                logger.warning(
                    "Playwright: Fetch cancelled on %s (attempt %s/%s).",
                    current_url_val,
                    attempt + 1,
                    effective_retries + 1,
                )
                raise
            except Exception as e:
                logger.error(
                    "Playwright: Unexpected error on %s (attempt %s/%s): %s",
                    current_url_val,
                    attempt + 1,
                    effective_retries + 1,
                    e,
                )

            if attempt < effective_retries:
                await asyncio.sleep(2)

        return None, final_url_val, status_code_val

    async def _attempt_cloudflare_solve_spatial(self, page: Page) -> bool:
        """
        Coordinate-based spatial solver for Cloudflare.
        Delegates to specialized solver module.
        """
        from .solver import CloudflareSolver

        return await CloudflareSolver.solve_spatial(page)

    async def _attempt_px_solve(self, page: Page) -> bool:
        """
        OS-level solver for PerimeterX Press & Hold challenges.
        Delegates to specialized px_solver module.
        Uses pyautogui (optional dep) for real Win32 mouse events.
        """
        from .px_solver import PerimeterXSolver

        if self.headless:
            logger.warning(
                "Playwright: PX Solver is disabled in headless mode for safety. "
                "Use headed mode for OS-level interaction."
            )
            return False

        if not PerimeterXSolver.is_available():
            logger.warning(
                "Playwright: PX Solver unavailable (pyautogui not installed or no display)."
            )
            return False

        warning_seconds_raw = os.environ.get("WST_OS_INPUT_WARNING_SECONDS", "3")
        try:
            warning_seconds = int(warning_seconds_raw)
        except Exception:
            warning_seconds = 3
        await PerimeterXSolver.warn_before_os_input_takeover(
            countdown_seconds=warning_seconds,
            reason="interactive browser challenge handling",
        )

        if not await PerimeterXSolver.ensure_safe_active_window(page):
            logger.warning(
                "Playwright: PX Solver aborted because browser window is not verified "
                "as foreground/active."
            )
            return False

        # Try CF checkbox first (some sites chain both)
        await PerimeterXSolver.solve_cloudflare_checkbox(page)
        await page.wait_for_timeout(1000)

        return await PerimeterXSolver.solve_press_and_hold(page)

