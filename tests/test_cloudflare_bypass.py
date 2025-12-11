import asyncio
import logging
import sys
import os

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from web_scraper_toolkit.browser.playwright_handler import PlaywrightManager

# Logging is configured in tests/__init__.py
logger = logging.getLogger(__name__)


async def test_cloudflare_bypass():
    config = {
        "scraper_settings": {
            "browser_type": "chromium",
            "headless": True,  # We WANT this to be True to test the Smart Fallback
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
        elif status == 403:
            logger.error("FAILED: Still blocked by 403.")

            # Use absolute path for debug output to avoid CWD issues
            debug_path = os.path.join(os.path.dirname(__file__), "debug_cf.html")
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"Saved HTML to {debug_path}")
        else:
            logger.warning(f"⚠️ INDETERMINATE: Status {status}. Check logs.")


if __name__ == "__main__":
    try:
        asyncio.run(test_cloudflare_bypass())
    except KeyboardInterrupt:
        pass
