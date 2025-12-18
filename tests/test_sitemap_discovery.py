# ./tests/test_sitemap_discovery.py
"""
Test suite for sitemap discovery logic.
"""

import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from web_scraper_toolkit.parsers.sitemap_handler import (
    find_sitemap_urls,
    extract_sitemap_tree,
    parse_sitemap_urls,
    _check_robots_txt,
    _check_common_paths,
    _check_homepage_for_sitemap,
)


class TestSitemapDiscovery(unittest.IsolatedAsyncioTestCase):
    async def test_parse_cdata_urls(self):
        """Test that CDATA tags are stripped from URLs (ported from test_cdata_sitemap.py)"""
        xml_content = """
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url>
                <loc><![CDATA[https://icomplycannabis.com/page-sitemap.xml]]></loc>
                <lastmod>2025-12-12T23:50:00+00:00</lastmod>
            </url>
             <url>
                <loc>https://icomplycannabis.com/simple-url.xml</loc>
            </url>
        </urlset>
        """
        urls = parse_sitemap_urls(xml_content)

        self.assertIn("https://icomplycannabis.com/page-sitemap.xml", urls)
        self.assertIn("https://icomplycannabis.com/simple-url.xml", urls)

        # Ensure regex didn't capture the CDATA part
        for url in urls:
            self.assertFalse(url.startswith("<![CDATA["))
            self.assertFalse(url.endswith("]]>"))

    async def test_check_robots_txt_found(self):
        """Test finding sitemap in robots.txt"""
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = (
                "User-agent: *\nSitemap: https://example.com/sitemap_from_robots.xml"
            )
            mock_get.return_value = mock_resp

            # Since _check_robots_txt uses asyncio.to_thread(requests.get), mocking requests.get works
            # providing we mock the Sync version that it calls.

            results = await _check_robots_txt("https://example.com")
            self.assertIn("https://example.com/sitemap_from_robots.xml", results)

    async def test_check_common_paths_found(self):
        """Test finding sitemap in common paths"""
        with patch("requests.head") as mock_head:

            def side_effect(url, **kwargs):
                mock_resp = MagicMock()
                if url.endswith("/sitemap.xml"):
                    mock_resp.status_code = 200
                    mock_resp.headers = {"Content-Type": "application/xml"}
                else:
                    mock_resp.status_code = 404
                return mock_resp

            mock_head.side_effect = side_effect

            results = await _check_common_paths("https://example.com")
            self.assertIn("https://example.com/sitemap.xml", results)
            self.assertEqual(len(results), 1)

    async def test_check_homepage_found(self):
        """Test finding sitemap in homepage links"""
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            # HTML with both <link> and <footer> link
            mock_resp.content = b"""
            <html>
                <head>
                    <link rel="sitemap" href="/sitemap_link.xml" />
                </head>
                <body>
                    <footer>
                        <a href="/footer_sitemap">Sitemap</a>
                    </footer>
                </body>
            </html>
            """
            mock_get.return_value = mock_resp

            results = await _check_homepage_for_sitemap("https://example.com")
            self.assertIn("https://example.com/sitemap_link.xml", results)
            self.assertIn("https://example.com/footer_sitemap", results)

    async def test_full_discovery_integration(self):
        """Test find_sitemap_urls aggregates all methods"""
        # We mock the internal helper functions to verify orchestration
        with (
            patch(
                "web_scraper_toolkit.parsers.sitemap_handler._check_robots_txt",
                new_callable=AsyncMock,
            ) as mock_robots,
            patch(
                "web_scraper_toolkit.parsers.sitemap_handler._check_common_paths",
                new_callable=AsyncMock,
            ) as mock_common,
            patch(
                "web_scraper_toolkit.parsers.sitemap_handler._check_homepage_for_sitemap",
                new_callable=AsyncMock,
            ) as mock_home,
        ):
            mock_robots.return_value = ["https://example.com/robots_sitemap.xml"]
            mock_common.return_value = ["https://example.com/common_sitemap.xml"]
            mock_home.return_value = [
                "https://example.com/robots_sitemap.xml",
                "https://example.com/home_sitemap.xml",
            ]

            results = await find_sitemap_urls("https://example.com")

            self.assertEqual(len(results), 3)  # Deduplicated
            self.assertIn("https://example.com/robots_sitemap.xml", results)
            self.assertIn("https://example.com/common_sitemap.xml", results)
            self.assertIn("https://example.com/home_sitemap.xml", results)

    async def test_extract_sitemap_tree_recursion(self):
        """Test recursive sitemap extraction"""

        # Mock fetch_sitemap_content
        with patch(
            "web_scraper_toolkit.parsers.sitemap_handler.fetch_sitemap_content",
            new_callable=AsyncMock,
        ) as mock_fetch:
            # Use side_effect to return different content for different URLs
            def fetch_side_effect(url, **kwargs):
                if url == "https://example.com/index.xml":
                    return """
                    <sitemapindex>
                        <sitemap>
                            <loc>https://example.com/child1.xml</loc>
                        </sitemap>
                    </sitemapindex>
                    """
                elif url == "https://example.com/child1.xml":
                    return """
                    <urlset>
                        <url>
                            <loc>https://example.com/page1</loc>
                        </url>
                    </urlset>
                    """
                return None

            mock_fetch.side_effect = fetch_side_effect

            urls = await extract_sitemap_tree("https://example.com/index.xml")

            self.assertEqual(urls, ["https://example.com/page1"])


if __name__ == "__main__":
    unittest.main()
