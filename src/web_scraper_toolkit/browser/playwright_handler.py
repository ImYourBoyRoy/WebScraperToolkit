# ./src/web_scraper_toolkit/browser/playwright_handler.py
"""
Playwright Handler
==================

Low-level interface to the Playwright browser automation library.
Handles browser lifecycle, page creation, stealth overrides, and Cloudflare navigation.

Usage:
    async with PlaywrightManager(config) as manager:
        content, url, status = await manager.smart_fetch("https://...")

Key Features:
    - Cloudflare 'Spatial Solver' (Click-to-verify logic).
    - Stealth overrides (Navigator properties).
    - PDF generation (Headless only).
    - Robust error handling and retries.
"""

import asyncio
import random
import logging
from typing import Optional, Dict, Any, Tuple, Union
from urllib.parse import urlparse

from playwright.async_api import (
    async_playwright,
    Playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    Response as PlaywrightResponse,
)

logger = logging.getLogger(__name__)

# --- UPDATED CONFIGURATION (Matches your working test_cloudflare.py) ---
DEFAULT_USER_AGENTS = [
    # We keep these for fallback, but we will default to 'None' (Native) for Cloudflare
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

DEFAULT_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--enable-webgl",  # CRITICAL: Fixes 'No Adapter' error
    "--window-size=1400,1000",
    "--no-sandbox",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    # "--disable-gpu",            # REMOVED: Conflicted with --enable-webgl in your working test
    "--ignore-certificate-errors",
]


class PlaywrightManager:
    """
    Manages Playwright browser instances, contexts, and pages for web interactions.
    Full-featured version with integrated Cloudflare Spatial Solver.
    """

    def __init__(self, config: Union[Dict[str, Any], "ScraperConfig"]):
        # Handle dict vs ScraperConfig
        if hasattr(config, "to_dict"):
            # It's a ScraperConfig object
            self.config = config
            self.settings = config.scraper_settings
        else:
            # Backward compat for dict
            # Warning: Ideally use ScraperConfig.load(config)
            from ..core.config import ScraperConfig

            self.config = ScraperConfig.load(config)
            self.settings = self.config.scraper_settings

        self.browser_type_name = self.settings.browser_type.lower()
        self.headless = self.settings.headless

        self.user_agents = self.settings.user_agents or DEFAULT_USER_AGENTS
        self.launch_args = list(set(DEFAULT_LAUNCH_ARGS + self.settings.launch_args))

        self.default_viewport = self.settings.default_viewport
        self.default_navigation_timeout_ms = (
            self.settings.default_timeout_seconds * 1000
        )
        self.default_action_retries = self.settings.retry_attempts

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None

        logger.info(
            f"PlaywrightManager initialized: Browser={self.browser_type_name}, Headless={self.headless}, "
            f"Default Timeout={self.default_navigation_timeout_ms}ms"
        )

    async def start(self):
        if self._browser and self._browser.is_connected():
            return

        if not self._playwright:
            self._playwright = await async_playwright().start()
            logger.info("Playwright started.")

        try:
            # Force Chromium for the bypass logic (Firefox/Webkit handle stealth differently)
            browser_launcher = getattr(
                self._playwright, self.browser_type_name, self._playwright.chromium
            )

            self._browser = await browser_launcher.launch(
                headless=self.headless, args=self.launch_args
            )
            logger.info(
                f"{self.browser_type_name} browser launched. Headless: {self.headless}."
            )
        except Exception as e:
            logger.error(
                f"Failed to launch {self.browser_type_name} browser: {e}", exc_info=True
            )
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            raise

    async def stop(self):
        if self._browser and self._browser.is_connected():
            try:
                await self._browser.close()
                logger.info(f"{self.browser_type_name} browser closed.")
            except Exception as e:
                logger.error(f"Error closing browser: {e}", exc_info=True)
        self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
                logger.info("Playwright stopped.")
            except Exception as e:
                logger.error(f"Error stopping Playwright: {e}", exc_info=True)
        self._playwright = None

    async def get_new_page(
        self, context_options: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[Page], Optional[BrowserContext]]:
        if not self._browser or not self._browser.is_connected():
            logger.warning("Browser not started or not connected. Attempting to start.")
            await self.start()
            if not self._browser or not self._browser.is_connected():
                logger.error("Failed to get new page: Browser could not be started.")
                return None, None

        # Browser Stealth Strategy:
        # We deliberately do NOT set a custom 'user_agent' here by default.
        # Leaving it None allows Chromium to report its native version (e.g. Chrome/131),
        # which matches the TLS fingerprint and helps pass Cloudflare challenges.
        base_context_options = {
            "viewport": self.default_viewport,
            "ignore_https_errors": True,
            "java_script_enabled": True,
            "locale": "en-US",
            "timezone_id": "America/New_York",
        }

        if context_options:
            base_context_options.update(context_options)

        try:
            context = await self._browser.new_context(**base_context_options)

            # Stealth: Scrub navigator.webdriver (Critical for Cloudflare)
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            # Tracker blocking (Restored from your original code)
            await context.route(
                "**/*",
                lambda route: route.abort()
                if self._is_tracker_or_ad(route.request.url)
                else route.continue_(),
            )

            page = await context.new_page()
            return page, context
        except Exception as e:
            logger.error(f"Error creating new page and context: {e}", exc_info=True)
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

    async def fetch_page_content(
        self,
        page: Page,
        url: str,
        action_name: str = "fetching page",
        retries: Optional[int] = None,
        navigation_timeout_ms: Optional[int] = None,
        wait_for_selector: Optional[str] = None,
        scroll_to_load: bool = False,
        wait_until_state: str = "domcontentloaded",
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
                    f"Playwright: Attempt {attempt + 1}/{effective_retries + 1} - {action_name} @ {current_url_val}"
                )

                response: Optional[PlaywrightResponse] = await page.goto(
                    current_url_val,
                    timeout=effective_nav_timeout,
                    wait_until=wait_until_state,
                )

                final_url_val = page.url
                if response:
                    status_code_val = response.status

                # --- 1. Infrastructure Check (Fail Fast on 5xx) ---
                if status_code_val in [500, 502, 503, 504]:
                    logger.error(
                        f"⚠️ SERVER ERROR {status_code_val}: The target site is down (Gateway/Service Unavailable)."
                    )
                    content = await page.content()
                    return content, final_url_val, status_code_val

                # Wait for selector if specified
                if wait_for_selector:
                    try:
                        await page.wait_for_selector(
                            wait_for_selector,
                            timeout=max(10000, effective_nav_timeout // 2),
                        )
                    except PlaywrightTimeoutError:
                        logger.warning(
                            f"Playwright: Selector '{wait_for_selector}' not found on {final_url_val}."
                        )
                else:
                    await page.wait_for_timeout(random.uniform(1500, 3000))

                if scroll_to_load:
                    await page.evaluate(
                        "window.scrollTo(0, document.body.scrollHeight)"
                    )
                    await page.wait_for_timeout(1000)

                content = await page.content()
                content_lower = content.lower() if content else ""

                # Check Safe Title
                try:
                    current_title = await page.title()
                except:
                    current_title = "Redirecting..."

                # --- 2. Cloudflare Detection & Solving ---
                if (
                    "just a moment" in current_title
                    or "attention required" in current_title
                    or ("cloudflare" in content_lower and "challenge" in content_lower)
                ):
                    logger.info(
                        f"Playwright: Cloudflare challenge detected at {final_url_val}. Engaging Spatial Solver..."
                    )

                    solved = await self._attempt_cloudflare_solve_spatial(page)

                    if solved:
                        logger.info(
                            "Playwright: Spatial Solver reports success. Re-fetching content."
                        )
                        await page.wait_for_timeout(3000)

                        # Refresh content variables
                        content = await page.content()
                        final_url_val = page.url

                        # If we passed, assume 200 OK
                        if "Just a moment" not in (await page.title()):
                            status_code_val = 200
                    else:
                        logger.warning(
                            "Playwright: Spatial Solver failed to confirm bypass."
                        )

                logger.info(
                    f"Playwright: Finished fetch for {final_url_val} (status: {status_code_val}, len: {len(content or '')})"
                )
                return content, final_url_val, status_code_val

            except PlaywrightTimeoutError as pte:
                logger.warning(
                    f"Playwright: Timeout on {current_url_val} "
                    f"(attempt {attempt + 1}/{effective_retries + 1}): {pte}"
                )
            except Exception as e:
                logger.error(
                    f"Playwright: Unexpected error on {current_url_val} "
                    f"(attempt {attempt + 1}/{effective_retries + 1}): {e}"
                )

            # Retry logic
            if attempt < effective_retries:
                await asyncio.sleep(2)

        return None, final_url_val, status_code_val

    async def _attempt_cloudflare_solve_spatial(self, page: Page) -> bool:
        """
        Coordinate-based spatial solver for Cloudflare.
        Simulates human mouse interaction to click verify widgets.
        """
        try:
            # Stabilize
            await page.wait_for_timeout(2000)

            # Find label
            label = page.get_by_text("Verifying you are human")
            if await label.count() == 0:
                label = page.get_by_text("Verify you are human")

            # Iframe Fallback
            if await label.count() == 0:
                for frame in page.frames:
                    try:
                        if (
                            await frame.get_by_text("Verifying you are human").count()
                            > 0
                        ):
                            label = frame.get_by_text("Verifying you are human")
                            break
                    except:
                        continue

            if await label.count() > 0:
                box = await label.bounding_box()
                if box:
                    # OFFSETS: +25px right, +70px down from text
                    target_x = box["x"] + 25
                    target_y = box["y"] + 70

                    logger.info(
                        f"Playwright: Clicking Widget at X={int(target_x)}, Y={int(target_y)}"
                    )

                    try:
                        # Human Click (Down -> Wait -> Up)
                        await page.mouse.move(target_x, target_y, steps=10)
                        await page.wait_for_timeout(300)
                        await page.mouse.down()
                        await page.wait_for_timeout(random.randint(150, 300))
                        await page.mouse.up()
                        logger.info(
                            "Playwright: Interaction sent. Waiting for redirect..."
                        )
                    except Exception as mouse_err:
                        # If the page navigates *during* the click (e.g. auto-solve or fast redirect),
                        # we might get "Target page, context or browser has been closed".
                        # This is usually a GOOD sign (we passed).
                        logger.info(
                            f"Playwright: Interaction interrupted (likely redirect): {mouse_err}"
                        )

                    # Wait for redirect loop (15s max)
                    for _ in range(15):
                        await page.wait_for_timeout(1000)
                        try:
                            title = await page.title()
                            # Success check: Title changed from challenge
                            if (
                                "Just a moment" not in title
                                and "Attention Required" not in title
                                and "403" not in title
                            ):
                                logger.info(
                                    f"Playwright: Success! Redirected to {title}"
                                )
                                return True
                        except:
                            continue
            else:
                logger.info(
                    "Playwright: No 'Verifying' text found. Checking if auto-solved..."
                )
                await page.wait_for_timeout(5000)
                try:
                    if "Just a moment" not in (await page.title()):
                        return True
                except:
                    pass

            return False

        except Exception as e:
            logger.error(f"Playwright: Spatial Solver Error: {e}")
            return False

            return False

    async def smart_fetch(
        self, url: str, **kwargs
    ) -> Tuple[Optional[str], str, Optional[int]]:
        """
        High-level fetch that automatically restarts the browser in HEADED mode
        if a blocking signature (403, Cloudflare Challenge) is detected while headless.

        Manages its own Page/Context lifecycle.
        """
        # Attempt 1: Current State
        page, context = await self.get_new_page()
        if not page:
            return None, url, None

        try:
            content, final_url, status = await self.fetch_page_content(
                page, url, **kwargs
            )

            # Detection: Did we fail due to anti-bot?
            is_blocked = False

            # Status check
            if status in [403, 429]:
                is_blocked = True

            # Content check (if status was 200 but actually a captcha)
            if content:
                content_lower = content.lower()
                # If we have a challenge text but the solver failed (or didn't run)
                if (
                    "just a moment" in content_lower
                    or "verification required" in content_lower
                ) and len(content) < 50000:
                    try:
                        title = await page.title()
                        if "Just a moment" in title or "Attention Required" in title:
                            is_blocked = True
                    except:
                        pass

            # FALLBACK LOGIC
            if is_blocked and self.headless:
                logger.warning(
                    f"SmartFetch: Block detected ({status}) on {url} while Headless. Switching to HEADED mode for retry..."
                )

                # Close Page/Context first
                await page.close()
                if context:
                    await context.close()
                page = None
                context = None

                # Restart Browser Visible
                await self.stop()
                self.headless = False
                await self.start()

                # Retry
                page, context = await self.get_new_page()
                if page:
                    logger.info("SmartFetch: Retrying in Headed mode...")
                    content, final_url, status = await self.fetch_page_content(
                        page, url, action_name="smart_retry", **kwargs
                    )

            return content, final_url, status

        finally:
            if page:
                try:
                    await page.close()
                except:
                    pass
            if context:
                try:
                    await context.close()
                except:
                    pass

    async def _auto_scroll(self, page: Page):
        """
        Scrolls the page to the bottom to trigger lazy loading.
        """
        logger.info("Auto-scrolling page to trigger lazy loading...")
        await page.evaluate("""
            async () => {
                await new Promise((resolve) => {
                    var totalHeight = 0;
                    var distance = 100;
                    var timer = setInterval(() => {
                        var scrollHeight = document.body.scrollHeight;
                        window.scrollBy(0, distance);
                        totalHeight += distance;

                        if(totalHeight >= scrollHeight - window.innerHeight){
                            clearInterval(timer);
                            resolve();
                        }
                    }, 100);
                });
            }
        """)
        # Wait a bit after scrolling for final renders
        await page.wait_for_timeout(2000)

    async def capture_screenshot(
        self, url: str, output_path: str, full_page: bool = True, **kwargs
    ) -> Tuple[bool, int]:
        """
        Captures a screenshot of the target URL.
        Returns: (Success, StatusCode)
        """
        page, context = await self.get_new_page()
        if not page:
            return False, 0

        try:
            # We reuse fetch_page_content just to load the page robustly
            _, final_url, status = await self.fetch_page_content(
                page, url, action_name="loading for screenshot", **kwargs
            )

            # Default to auto-scroll for screenshots to capture full lazy-loaded content
            await self._auto_scroll(page)

            logger.info(f"Taking screenshot of {final_url} to {output_path}")
            await page.screenshot(path=output_path, full_page=full_page)
            return True, status
        except Exception as e:
            logger.error(f"Screenshot failed: {e}", exc_info=True)
            return False, 0
        finally:
            if page:
                await page.close()
            if context:
                await context.close()

    async def save_pdf(self, url: str, output_path: str, **kwargs) -> Tuple[bool, int]:
        """
        Saves the target URL as a PDF.
        Returns: (Success, StatusCode)
        Note: PDF generation ONLY works in HEADLESS mode in Chromium.
        """

        page, context = await self.get_new_page()
        if not page:
            return False, 0

        try:
            # Use networkidle to ensure hydration (fancy java stuff)
            _, _, status = await self.fetch_page_content(
                page,
                url,
                action_name="loading for PDF",
                wait_until_state="networkidle",
                **kwargs,
            )

            # Default to auto-scroll for PDFs
            await self._auto_scroll(page)

            # Force 'screen' media to avoid print stylesheets that hide backgrounds/layout
            await page.emulate_media(media="screen")

            logger.info(f"Saving PDF of {url} to {output_path}")
            # print_background=True captures colors/images
            await page.pdf(path=output_path, format="A4", print_background=True)
            return True, status
        except Exception as e:
            logger.error(f"PDF generation failed: {e}", exc_info=True)
            return False, 0
        finally:
            if page:
                await page.close()
            if context:
                await context.close()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
