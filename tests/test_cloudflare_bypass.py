import unittest
import logging
import sys
import os

import pytest

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from web_scraper_toolkit.browser.playwright_handler import PlaywrightManager

# Logging is configured in tests/__init__.py
logger = logging.getLogger(__name__)

# By default, skip this test in CI unless SKIP_CF_TEST=0 is explicitly set
SKIP_CF_TEST = os.getenv("SKIP_CF_TEST", "1") == "1"


@pytest.mark.skipif(SKIP_CF_TEST, reason="Cloudflare bypass test disabled in CI")
class TestCloudflareBypass(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Optional: clean local __pycache__ to avoid stale artifacts
        import shutil

        cache_path = os.path.join(os.path.dirname(__file__), "__pycache__")
        if os.path.exists(cache_path):
            try:
                shutil.rmtree(cache_path)
            except Exception:
                # We don't want setup to fail just because cache couldn't be removed
                pass

    async def test_cloudflare_bypass(self):
        config = {
            "scraper_settings": {
                "browser_type": "chromium",
                "headless": True,  # We WANT this True to test Smart Fallback
                "default_timeout_seconds": 60,
            }
        }

        target_url = "https://2captcha.com/demo/cloudflare-turnstile-challenge"

        logger.info(f"Starting Cloudflare Bypass Test for: {target_url}")

        async with PlaywrightManager(config) as pm:
            # Use smart_fetch which handles page creation and auto-retry if blocked
            logger.info("Navigating to target using smart_fetch...")
            content, final_url, status = await pm.smart_fetch(target_url)

            logger.info(f"Final Status: {status}")
            logger.info(f"Final URL: {final_url}")
            logger.info(f"Content Length: {len(content) if content else 0}")

            if status == 200 and content and len(content) > 20000:
                logger.info("SUCCESS: Cloudflare bypassed and content retrieved!")
                self.assertTrue(True)
            elif status == 403:
                logger.error("FAILED: Still blocked by 403.")

                # Use absolute path for debug output
                debug_path = os.path.join(
                    os.path.dirname(__file__),
                    "debug_cf.html",
                )
                try:
                    with open(debug_path, "w", encoding="utf-8") as f:
                        f.write(content or "")
                    logger.info(f"Saved HTML to {debug_path}")
                except Exception as e:
                    logger.error(f"Failed to write debug_cf.html: {e}")

                self.fail("Cloudflare Bypass Failed: Status 403. See debug_cf.html")
            else:
                logger.warning(f"INDETERMINATE: Status {status}. Check logs.")
                self.fail(f"Cloudflare Bypass Indeterminate: Status {status}")


if __name__ == "__main__":
    unittest.main()
