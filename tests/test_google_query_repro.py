import asyncio
import logging
import sys

from web_scraper_toolkit.browser.config import BrowserConfig
from web_scraper_toolkit.browser.playwright_handler import PlaywrightManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def test_google_query():
    query = "Best open source web scraping tools site:github.com"
    url = f"https://www.google.com/search?hl=en&num=15&q={query.replace(' ', '+')}"

    config = BrowserConfig.from_dict(
        {
            "headless": True,  # Test with headless first as agents usually run headless
            "browser_type": "chromium",
            "native_fallback_policy": "on_blocked",
            "stealth_mode": True,
            "serp_retry_policy": "balanced",
        }
    )

    print(f"Testing Google Query: {url}")
    async with PlaywrightManager(config) as manager:
        content, final_url, status = await manager.smart_fetch(url)
        print(f"Status: {status}")
        print(f"Final URL: {final_url}")
        print(f"Content length: {len(content) if content else 0}")
        if status == 429 or "sorry/index" in final_url:
            print("BLOCKED: Google Sorry page detected.")
            assert False, "BLOCKED: Google Sorry page detected."
        elif status == 200:
            print("SUCCESS: Google query completed.")
            assert True
        else:
            print(f"UNKNOWN: status {status}")
            sys.exit(2)


if __name__ == "__main__":
    asyncio.run(test_google_query())
