# ./tests/verify_hybrid.py
"""
Verification Script for Phase 9: Hybrid Engine.
Tests that AutonomousCrawler uses the Fast Lane (aiohttp) for static content.
"""

import sys
import os
import asyncio
import logging
import io

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from web_scraper_toolkit.crawler.engine import AutonomousCrawler
from web_scraper_toolkit.playbook.models import Playbook

# Configure StreamHandler to capture logs for verification
log_capture_string = io.StringIO()
ch = logging.StreamHandler(log_capture_string)
ch.setLevel(logging.INFO)
logging.getLogger("web_scraper_toolkit.crawler.engine").addHandler(ch)
logging.getLogger("web_scraper_toolkit.crawler.engine").setLevel(logging.INFO)

# Also basic logging to stdout
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_hybrid")


async def test_hybrid_crawl():
    logger.info("--- Starting Hybrid Direct Crawl Verification ---")

    # 1. create Playbook - Use a simple static site
    playbook_data = {
        "name": "Hybrid Test",
        "base_urls": ["http://example.com"],
        "settings": {"max_depth": 0, "max_pages": 1, "crawl_delay": 0.0},
        "rules": [
            {
                "type": "extract",
                "extract_fields": [{"name": "title", "selector": "h1", "type": "css"}],
            }
        ],
    }

    playbook = Playbook(**playbook_data)

    # 2. Initialize Crawler
    crawler = AutonomousCrawler(playbook=playbook)

    # 3. Run
    await crawler.run()

    # 4. Verify Logs for "Fast Lane Success"
    log_contents = log_capture_string.getvalue()
    logger.info(f"Captured Logs:\n{log_contents}")

    if "Fast Lane Success" in log_contents:
        logger.info("SUCCESS: Fast Lane (aiohttp) was used!")
    else:
        logger.error("FAILURE: Fast Lane was NOT used (or not logged).")
        if "Switching to Power Lane" in log_contents:
            logger.warning(
                "Switched to Playwright - Check if aiohttp failed unexpectedly."
            )
        sys.exit(1)

    # Cleanup
    if os.path.exists(crawler.results_filename):
        os.remove(crawler.results_filename)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(test_hybrid_crawl())
