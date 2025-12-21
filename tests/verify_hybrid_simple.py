# ./tests/verify_hybrid_simple.py
import sys
import os
import asyncio
import logging

# Force Logger
root = logging.getLogger()
root.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
root.addHandler(handler)

# Specific
logging.getLogger("web_scraper_toolkit").setLevel(logging.INFO)
logging.getLogger("web_scraper_toolkit").addHandler(handler)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from web_scraper_toolkit.crawler.engine import AutonomousCrawler  # noqa: E402
from web_scraper_toolkit.playbook.models import Playbook  # noqa: E402
import logging  # noqa: E402

logging.basicConfig(level=logging.INFO)


async def main():
    if os.path.exists("crawl_state.json"):
        os.remove("crawl_state.json")
    print("Starting Main...")
    playbook_data = {
        "name": "Hybrid Test",
        "base_urls": ["http://example.com"],
        "settings": {"max_depth": 0, "max_pages": 1, "crawl_delay": 0.0},
        "rules": [],
    }
    playbook = Playbook(**playbook_data)
    print("Playbook Created.")

    crawler = AutonomousCrawler(playbook=playbook)
    print("Crawler Initialized.")

    # Check if fast_scraper exists
    if hasattr(crawler, "fast_scraper"):
        print(f"Fast Scraper present: {type(crawler.fast_scraper)}")
    else:
        print("ERROR: Fast Scraper missing!")

    print("Running crawler...")
    await crawler.run()
    print("Crawler Finished.")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
