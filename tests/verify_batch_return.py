# tests/verify_batch_return.py
import unittest
import sys
import os

# Insert src path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from web_scraper_toolkit.browser.playwright_crawler import WebCrawler


class TestBatchReturn(unittest.IsolatedAsyncioTestCase):
    async def test_crawler_returns_results(self):
        # Mock class to avoid actual browser calls if possible,
        # but WebCrawler is tightly coupled to PlaywrightManager.
        # We will use "text" format which uses requests in a thread (cheaper/safer if no network).
        # Actually "text" format uses `read_website_content` which does requests.get.
        # We can mock `read_website_content` or just run against a safe target (example.com).

        # Let's mock `process_single_url` to return immediately to avoid network.

        crawler = WebCrawler()

        # Mocking process_single_url is hard because it's an instance method we want to test interaction of run()
        # But we can assume run() calls process_single_url.
        # Let's test the return structure of run() directly by mocking the gathering.

        async def mock_process(index, total, url, *args, **kwargs):
            return (f"Content for {url}", None)

        crawler.process_single_url = mock_process

        urls = ["http://a.com", "http://b.com"]
        results = await crawler.run(urls=urls, output_format="text")

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], ("Content for http://a.com", None))
        self.assertEqual(results[1], ("Content for http://b.com", None))
        print("Success: WebCrawler.run returned expected mapped results.")


if __name__ == "__main__":
    unittest.main()
