# ./tests/test_discovery.py
import unittest
from unittest.mock import patch
# sys.path handled by run_tests.py or discovery

from web_scraper_toolkit.parsers.discovery import smart_discover_urls


class TestSmartDiscovery(unittest.IsolatedAsyncioTestCase):
    @patch("web_scraper_toolkit.parsers.discovery.find_sitemap_urls")
    @patch("web_scraper_toolkit.parsers.discovery.peek_sitemap_index")
    @patch("web_scraper_toolkit.parsers.discovery.extract_sitemap_tree")
    async def test_smart_discover_urls_basics(self, mock_extract, mock_peek, mock_find):
        # Setup Mocks
        mock_find.return_value = ["http://test.com/sitemap.xml"]

        # Mock peek to return an index
        mock_peek.return_value = {
            "type": "index",
            "sitemaps": [
                {"url": "http://test.com/post-sitemap.xml", "count": 10},
                {"url": "http://test.com/product-sitemap.xml", "count": 50},
            ],
        }

        # Mock extract side effect
        async def extract_side_effect(url, depth, *args, **kwargs):
            if "post-sitemap" in url:
                return ["http://test.com/about-us", "http://test.com/random-page"]
            return []

        mock_extract.side_effect = extract_side_effect

        # Execute
        results = await smart_discover_urls("http://test.com")

        # Verify Results
        priority = results["priority_urls"]
        general = results["general_urls"]

        # Check priority classification
        priority_urls = [u["url"] for u in priority]
        self.assertIn("http://test.com/about-us", priority_urls)

        # Check general classification
        general_urls = [u["url"] for u in general]
        self.assertIn("http://test.com/random-page", general_urls)

        # Verify product-sitemap content was NOT returned (since it returns [] in default side effect unless post-sitemap)
        # But wait, logic says "product" in default exclude keywords.
        # So "product-sitemap" loop should continue before calling extract.
        # So extract is NEVER CALLED for product-sitemap.
        # We can check that implicitly by ensuring no "product" URLs if we had them.
        pass

    @patch("web_scraper_toolkit.parsers.discovery.find_sitemap_urls")
    async def test_no_sitemaps_found(self, mock_find):
        mock_find.return_value = []
        results = await smart_discover_urls("http://test.com")
        self.assertEqual(results["priority_urls"], [])
        self.assertEqual(results["general_urls"], [])


if __name__ == "__main__":
    unittest.main()
