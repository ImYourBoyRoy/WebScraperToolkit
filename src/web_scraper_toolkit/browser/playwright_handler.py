# ./src/web_scraper_toolkit/browser/playwright_handler.py
"""
Public Playwright manager facade preserving legacy import/patch compatibility.
Run: imported by crawler/parsers/MCP handlers for browser automation workflows.
Inputs: BrowserConfig/dict payloads, fetch URLs, and optional proxy manager integration.
Outputs: PlaywrightManager APIs, bot-block classifier, and compatibility constants/types.
Side effects: launches browsers, performs network requests, and writes artifacts when requested.
Operational notes: implementation is split across private `_playwright_handler` modules.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, cast

from playwright.async_api import async_playwright

from ._playwright_handler import (
    BASELINE_LAUNCH_ARGS,
    COMMON_VIEWPORTS,
    DEFAULT_USER_AGENTS,
    EXPERIMENTAL_SERP_LAUNCH_ARGS,
    NATIVE_FALLBACK_LAUNCH_ARGS,
    SERP_NATIVE_LAUNCH_ARGS,
    BotBlockReason,
    PlaywrightInitStateMixin,
    PlaywrightLifecycleMixin,
    PlaywrightNativeAttemptsMixin,
    PlaywrightPageOpsMixin,
    PlaywrightRoutingMixin,
    PlaywrightSerpAttemptsMixin,
    PlaywrightSmartFetchArtifactsMixin,
    PlaywrightStrategySupportMixin,
    SerpProvider,
    WaitUntilState,
    _CF_CHALLENGE_MARKERS,
    _DDG_ANOMALY_MARKERS,
    _GOOGLE_UNUSUAL_TRAFFIC_MARKERS,
    _PX_CHALLENGE_MARKERS,
    classify_bot_block,
)

logger = logging.getLogger(__name__)
_STEALTH_BACKEND_LOGGED = False


class PlaywrightManager(
    PlaywrightInitStateMixin,
    PlaywrightRoutingMixin,
    PlaywrightLifecycleMixin,
    PlaywrightPageOpsMixin,
    PlaywrightStrategySupportMixin,
    PlaywrightNativeAttemptsMixin,
    PlaywrightSerpAttemptsMixin,
    PlaywrightSmartFetchArtifactsMixin,
):
    """
    Manages Playwright browser instances, contexts, and pages for web interactions.
    Full-featured version with integrated Cloudflare Spatial Solver.
    """

    async def start(self) -> None:
        """
        Start browser runtime.

        Kept on facade module so test patches to
        `web_scraper_toolkit.browser.playwright_handler.async_playwright`
        continue to intercept startup behavior.
        """
        if self._browser and self._browser.is_connected():
            return

        if not self._playwright:
            self._playwright = await async_playwright().start()
            logger.info("Playwright started.")

        try:
            launch_kwargs: Dict[str, Any] = {
                "headless": self.headless,
                "args": self.launch_args,
            }
            if self.browser_type_name in {"chrome", "msedge"}:
                launch_kwargs["channel"] = self.browser_type_name
                browser_launcher = self._playwright.chromium
            else:
                browser_launcher = getattr(
                    self._playwright,
                    self.browser_type_name,
                    self._playwright.chromium,
                )

            self._browser = await browser_launcher.launch(**cast(Any, launch_kwargs))
            self._browser_launch_fallback_used = False
            logger.info(
                "%s browser launched. Headless: %s.",
                self.browser_type_name,
                self.headless,
            )
        except Exception as exc:
            if self.browser_type_name in {"chrome", "msedge"} and self._playwright:
                logger.warning(
                    "Failed to launch channel '%s' (%s). Falling back to Playwright chromium.",
                    self.browser_type_name,
                    exc,
                )
                try:
                    self._browser = await self._playwright.chromium.launch(
                        **cast(Any, {"headless": self.headless, "args": self.launch_args})
                    )
                    self._browser_launch_fallback_used = True
                    logger.info(
                        "Chromium fallback launch succeeded after %s channel failure.",
                        self.browser_type_name,
                    )
                    return
                except Exception as fallback_exc:
                    logger.error(
                        "Fallback launch to chromium also failed: %s",
                        fallback_exc,
                        exc_info=True,
                    )

            logger.error(
                "Failed to launch %s browser: %s",
                self.browser_type_name,
                exc,
                exc_info=True,
            )
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            raise


__all__ = [
    "PlaywrightManager",
    "BotBlockReason",
    "SerpProvider",
    "WaitUntilState",
    "classify_bot_block",
    "DEFAULT_USER_AGENTS",
    "COMMON_VIEWPORTS",
    "BASELINE_LAUNCH_ARGS",
    "EXPERIMENTAL_SERP_LAUNCH_ARGS",
    "SERP_NATIVE_LAUNCH_ARGS",
    "NATIVE_FALLBACK_LAUNCH_ARGS",
    "_GOOGLE_UNUSUAL_TRAFFIC_MARKERS",
    "_DDG_ANOMALY_MARKERS",
    "_CF_CHALLENGE_MARKERS",
    "_PX_CHALLENGE_MARKERS",
]
