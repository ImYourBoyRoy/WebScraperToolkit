# ./tests/test_cdata_sitemap.py
"""
Test for CDATA extraction bug in sitemaps.
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath("src"))

import web_scraper_toolkit
from web_scraper_toolkit.parsers.sitemap_handler import parse_sitemap_urls

print(f"DEBUG: web_scraper_toolkit location: {web_scraper_toolkit.__file__}")


class TestCdataSitemap(unittest.TestCase):
    def test_parse_cdata_urls(self):
        """Test that CDATA tags are stripped from URLs"""
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


if __name__ == "__main__":
    unittest.main()
