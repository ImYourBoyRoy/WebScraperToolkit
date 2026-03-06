# ./src/web_scraper_toolkit/browser/_playwright_handler/lifecycle.py
"""
Browser lifecycle helpers for PlaywrightManager startup and shutdown.
Used by facade-composed manager class.
Run: imported by browser facade only.
Inputs: manager state for browser type, launch args, and playwright handles.
Outputs: started/stopped browser lifecycle states.
Side effects: launches/closes Playwright browser processes.
Operational notes: start logic may be overridden by facade for patch compatibility.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, cast

from playwright.async_api import async_playwright

logger = logging.getLogger("web_scraper_toolkit.browser.playwright_handler")


class PlaywrightLifecycleMixin:
    async def start(self) -> None:
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
                # Route Chrome/Edge through chromium channel launch so
                # browser_type='chrome' truly uses user-installed Chrome.
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
        except Exception as e:
            if self.browser_type_name in {"chrome", "msedge"} and self._playwright:
                logger.warning(
                    "Failed to launch channel '%s' (%s). Falling back to Playwright chromium.",
                    self.browser_type_name,
                    e,
                )
                try:
                    self._browser = await self._playwright.chromium.launch(
                        **cast(
                            Any,
                            {
                                "headless": self.headless,
                                "args": self.launch_args,
                            },
                        )
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
                e,
                exc_info=True,
            )
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            raise

    async def stop(self) -> None:
        if self._browser and self._browser.is_connected():
            try:
                await self._browser.close()
                logger.info("%s browser closed.", self.browser_type_name)
            except Exception as e:
                logger.error("Error closing browser: %s", e, exc_info=True)
        self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
                logger.info("Playwright stopped.")
            except Exception as e:
                logger.error("Error stopping Playwright: %s", e, exc_info=True)
        self._playwright = None
