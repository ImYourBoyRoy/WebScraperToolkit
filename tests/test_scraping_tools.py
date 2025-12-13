import unittest
from unittest.mock import patch, AsyncMock
import sys
import os
import asyncio

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

# We need to test specific logic inside scraping_tools.
# Since the logic is inside _arun_scrape, we can mock PlaywrightManager
# to return specific HTML content and verify the extraction output.

from web_scraper_toolkit.parsers.scraping_tools import _arun_scrape, get_sitemap_urls


class TestScrapingTools(unittest.TestCase):
    def setUp(self):
        # Cache Scrub (Roy-Standard)
        import shutil

        cache_path = os.path.join(os.path.dirname(__file__), "__pycache__")
        if os.path.exists(cache_path):
            try:
                shutil.rmtree(cache_path)
            except Exception:
                pass

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    @patch("web_scraper_toolkit.browser.playwright_handler.PlaywrightManager")
    def test_arun_scrape_extraction(self, MockPlaywrightManager):
        # Setup Mock
        mock_manager = MockPlaywrightManager.return_value
        mock_manager.start = AsyncMock()
        mock_manager.stop = AsyncMock()
        mock_manager.get_new_page = AsyncMock()
        mock_manager.fetch_page_content = AsyncMock()

        # Mock Page/Context
        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_manager.get_new_page.return_value = (mock_page, mock_context)

        # FIX: We now use smart_fetch in the tools, so we must mock it instead of/in addition to fetch_page_content
        mock_manager.smart_fetch = AsyncMock()

        # Mock Content
        html_content = """
        <html>
            <head><title>Test Company</title></head>
            <body>
                <p>Welcome to Test Company.</p>
                <p>Our CEO is John Doe.</p>
                <p>Contact us at contact@example.com</p>
            </body>
        </html>
        """
        # mock_manager.smart_fetch.return_value = (html_content, "https://example.com", 200)
        mock_manager.smart_fetch.return_value = (
            html_content,
            "https://example.com",
            200,
        )

        # Run extraction
        result = self.loop.run_until_complete(_arun_scrape("https://example.com"))

        # Verify assertions
        self.assertIn("TITLE: Test Company", result)
        self.assertIn("John Doe", result)  # Leadership extraction
        self.assertIn("contact@example.com", result)  # Email extraction

    @patch(
        "web_scraper_toolkit.parsers.scraping_tools.extract_sitemap_tree",
        new_callable=AsyncMock,
    )
    @patch(
        "web_scraper_toolkit.parsers.scraping_tools.find_sitemap_urls",
        new_callable=AsyncMock,
    )
    def test_sitemap_extraction(self, mock_find, mock_extract):
        # Mock finding a sitemap
        mock_find.return_value = ["https://example.com/sitemap.xml"]

        # Mock extracting URLs from it
        mock_extract.return_value = [
            "https://example.com/about",
            "https://example.com/contact",
            "https://example.com/product/123",
        ]

        result = get_sitemap_urls("https://example.com")

        # The function sums up found URLs.
        # Total unique = 3.
        self.assertIn("Found 3 unique URLs", result)
        self.assertIn("https://example.com/about", result)
        self.assertIn("https://example.com/contact", result)
        # Products are usually excluded
        self.assertNotIn("https://example.com/product/123", result)


if __name__ == "__main__":
    unittest.main()
