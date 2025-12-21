import unittest

# Ensure src is in path for testing without installing
# sys.path handled by run_tests.py

from web_scraper_toolkit.parsers.utils import normalize_url, truncate_text
from web_scraper_toolkit.parsers import SerpParser


class TestUtils(unittest.TestCase):
    def test_normalize_url(self):
        self.assertEqual(
            normalize_url("https://example.com/foo/"), "https://example.com/foo"
        )
        self.assertEqual(normalize_url("example.com"), None)  # Needs scheme

    def test_truncate_text(self):
        text = "Hello World"
        self.assertEqual(truncate_text(text, 5), "Hello...")
        self.assertEqual(truncate_text(text, 50), "Hello World")


class TestSerpParser(unittest.TestCase):
    def test_parse_empty(self):
        results = SerpParser.parse_ddg_html("", "https://example.com")
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
