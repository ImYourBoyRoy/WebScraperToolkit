# ./tests/verify_unification.py
"""
Verification Script for Phase 8: Architecture Unification.
Tests that AutonomousCrawler runs correctly with the new PlaywrightManager backend
in DIRECT mode (no proxies).
"""

import sys
import os
import asyncio
import json
import logging

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from web_scraper_toolkit.crawler.engine import AutonomousCrawler
from web_scraper_toolkit.playbook.models import Playbook

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_unification")


async def test_direct_crawl():
    logger.info("--- Starting Direct Crawl Verification ---")

    # 1. create Playbook
    playbook_data = {
        "name": "Unification Test",
        "base_urls": ["http://example.com"],
        "settings": {"max_depth": 0, "max_pages": 1, "crawl_delay": 0.0},
        "rules": [
            {
                "type": "extract",
                "extract_fields": [
                    {"name": "title", "selector": "h1", "type": "css"},
                    {"name": "paragraph", "selector": "p", "type": "css"},
                ],
            }
        ],
    }

    playbook = Playbook(**playbook_data)

    # 2. Initialize Crawler (Direct Mode - No Proxy Manager)
    crawler = AutonomousCrawler(playbook=playbook)

    # 3. Run
    await crawler.run()

    # 4. Verify Results
    results_file = crawler.results_filename
    if not os.path.exists(results_file):
        logger.error(f"FAILURE: Results file {results_file} not created.")
        sys.exit(1)

    with open(results_file, "r") as f:
        line = f.readline()
        data = json.loads(line)

    logger.info(f"Extracted Data: {data['data']}")

    if "data" in data and "title" in data["data"]:
        logger.info("SUCCESS: Data extracted via PlaywrightManager!")
    else:
        logger.error("FAILURE: Data missing from results.")
        sys.exit(1)

    # Cleanup
    if os.path.exists(results_file):
        os.remove(results_file)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(test_direct_crawl())
