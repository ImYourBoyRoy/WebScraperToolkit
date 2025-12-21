# tests/verify_crawler.py
"""
Verification Script for Proxie Crawler & Playbook.
"""

import asyncio
import logging
import os
import sys

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from web_scraper_toolkit.playbook.models import (
    Playbook,
    Rule,
    PlaybookSettings,
    FieldExtractor,
)
from web_scraper_toolkit.crawler import ProxieCrawler
from web_scraper_toolkit.crawler.config import CrawlerConfig

# Configure Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("CrawlerVerify")


async def main():
    logger.info("--- Starting Crawler Verification ---")

    # 1. Setup Mock Proxy Manager (No real credentials needed for logic test, but engine requires it)
    # We will use a "Direct" mock or just standard proxy if available?
    # Let's load real config if present, or fake it.

    # We want to test logic, not connectivity, primarily.
    # But `ProxieScraper` needs a proxy.
    # Let's use a Dummy Proxy Object that points to localhost (if we had a local server)
    # Or just reliance on robustness handling of failures.

    # Mocking Proxy for Logic Verification (Network independence)
    from unittest.mock import MagicMock

    # Fake content for httpbin pages
    async def mock_fetch(url):
        logger.info(f"Mock Fetch: {url}")
        if url == "https://httpbin.org/links/2/0":
            return '<html><h1>Main Page</h1><a href="/links/2/1">Link 1</a><a href="/links/2/2">Link 2</a></html>'
        elif "/links/" in url:
            return f"<html><h1>Sub Page {url}</h1></html>"
        return None

    # config = ProxieConfig(...) # Not needed for mock
    manager = MagicMock()  # ProxyManager config not needed if mocked
    manager.get_proxy.return_value = None

    # 2. Define Playbook
    # We will target httpbin.org to check extraction and following
    playbook = Playbook(
        name="HttpBin Test",
        base_urls=["https://httpbin.org/links/2/0"],  # Page with links
        rules=[
            # Rule 1: Follow links to 'links' pages
            Rule(type="follow", regex=r"/links/\d+/\d+"),
            # Rule 2: Extract Title from pages
            Rule(
                type="extract",
                regex=r".*",
                extract_fields=[
                    FieldExtractor(name="page_title", selector="h1", type="css")
                ],
            ),
        ],
        settings=PlaybookSettings(
            max_depth=1,
            max_pages=3,  # Limit to 3 pages
            crawl_delay=1.0,
            respect_robots=False,  # Httpbin disallows scraping usually
        ),
    )

    logger.info(f"Playbook: {playbook.name}")

    # 3. Initialize & Run Crawler
    crawl_config = CrawlerConfig()
    crawler = ProxieCrawler(
        playbook, manager, config=crawl_config, state_file="test_crawl_state.json"
    )

    # Inject Mock Fetcher
    crawler.fast_scraper.secure_fetch = mock_fetch

    logger.info("Running Crawler...")
    await crawler.run()

    # 4. Results
    logger.info(f"Crawler finished. Results: {len(crawler.results)}")
    for res in crawler.results:
        logger.info(f"  - {res}")

    # Cleanup state
    if os.path.exists("test_crawl_state.json"):
        os.remove("test_crawl_state.json")


if __name__ == "__main__":
    asyncio.run(main())
