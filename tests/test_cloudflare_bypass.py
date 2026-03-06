# ./tests/test_cloudflare_bypass.py
"""
Optional live Cloudflare bypass integration test for PlaywrightManager smart_fetch.
Run: pytest tests/test_cloudflare_bypass.py -q
Inputs: SKIP_CF_TEST env var and outbound network access to 2captcha demo URL.
Outputs: pass/fail assertions and optional debug_cf.html artifact on failure.
Side effects: launches real browser sessions and performs live web requests.
Operational notes: skipped by default (SKIP_CF_TEST=1) to keep CI deterministic.
"""

from __future__ import annotations

import logging
import os
import shutil
import unittest
from pathlib import Path

import pytest

from web_scraper_toolkit.browser.playwright_handler import PlaywrightManager

logger = logging.getLogger(__name__)

# Skip by default unless explicitly opted in for live integration runs.
SKIP_CF_TEST = os.getenv("SKIP_CF_TEST", "1") == "1"


@pytest.mark.integration
@pytest.mark.skipif(SKIP_CF_TEST, reason="Cloudflare bypass integration test disabled")
class TestCloudflareBypass(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        cache_path = Path(__file__).resolve().parent / "__pycache__"
        if cache_path.exists():
            try:
                shutil.rmtree(cache_path)
            except Exception:
                pass

    async def test_cloudflare_bypass(self) -> None:
        config = {
            "scraper_settings": {
                "browser_type": "chromium",
                "headless": True,
                "default_timeout_seconds": 60,
            }
        }
        target_url = "https://2captcha.com/demo/cloudflare-turnstile-challenge"

        logger.info("Starting Cloudflare bypass test for: %s", target_url)
        async with PlaywrightManager(config) as manager:
            content, final_url, status = await manager.smart_fetch(target_url)

        logger.info("Final status: %s", status)
        logger.info("Final URL: %s", final_url)
        logger.info("Content length: %d", len(content) if content else 0)

        if status == 200 and content and len(content) > 20_000:
            logger.info(
                "SUCCESS: Cloudflare bypassed and substantial content retrieved."
            )
            self.assertTrue(True)
            return

        if status == 403:
            debug_path = Path(__file__).resolve().parent / "debug_cf.html"
            try:
                debug_path.write_text(content or "", encoding="utf-8")
                logger.info("Saved debug HTML: %s", debug_path)
            except Exception as exc:
                logger.error("Failed to write debug_cf.html: %s", exc)
            self.fail("Cloudflare bypass failed with status 403. See debug_cf.html")

        self.fail(f"Cloudflare bypass indeterminate: status={status}")


if __name__ == "__main__":
    unittest.main()
