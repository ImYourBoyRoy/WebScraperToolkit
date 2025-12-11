import unittest
import sys
import os

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from web_scraper_toolkit.parsers.serp_parser import SerpParser


class TestSerpParser(unittest.TestCase):
    def test_parse_ddg_html_sample(self):
        # Simulated DuckDuckGo HTML structure
        html = """
        <html>
            <body>
                <div class="result">
                    <h2 class="result__title">
                        <a class="result__a" href="https://example.com/foo">Example Domain</a>
                    </h2>
                    <div class="result__snippet">This is a sample snippet for the example domain.</div>
                </div>
                <div class="result">
                    <h2 class="result__title">
                        <a class="result__a" href="https://www.google.com/search?q=test">Google Result Title</a>
                    </h2>
                    <div class="result__snippet">Another snippet here.</div>
                </div>
            </body>
        </html>
        """
        results = SerpParser.parse_ddg_html(html, "https://duckduckgo.com")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["url"], "https://example.com/foo")
        self.assertEqual(results[0]["title"], "Example Domain")
        self.assertIn("sample snippet", results[0]["snippet"])

    def test_parse_google_style_sample(self):
        # Simulated Google HTML structure (div.g)
        html = """
        <html>
            <body>
                <div class="g">
                    <div class="yuRUbf">
                        <a href="https://example.com/result">
                            <h3>Google Result Title</h3>
                        </a>
                    </div>
                    <div class="VwiC3b">Google snippet text...</div>
                </div>
            </body>
        </html>
        """
        results = SerpParser.parse_google_direct_links_style(html, "https://google.com")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://example.com/result")
        self.assertEqual(results[0]["title"], "Google Result Title")
        self.assertEqual(results[0]["snippet"], "Google snippet text...")

    def test_empty_content(self):
        results = SerpParser.parse_ddg_html("", "https://duckduckgo.com")
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
