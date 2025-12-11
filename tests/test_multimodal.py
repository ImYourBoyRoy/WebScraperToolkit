import unittest
import os
import shutil
from unittest.mock import patch, AsyncMock

# Adjust path to import from src
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from web_scraper_toolkit.parsers.scraping_tools import (
    extract_metadata,
    capture_screenshot,
    save_as_pdf,
)


class TestMultimodal(unittest.TestCase):
    def setUp(self):
        # Cache Scrub (Roy-Standard)
        import shutil

        cache_path = os.path.join(os.path.dirname(__file__), "__pycache__")
        if os.path.exists(cache_path):
            try:
                shutil.rmtree(cache_path)
            except:
                pass

        self.output_dir = "test_outputs"
        os.makedirs(self.output_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.output_dir):
            shutil.rmtree(self.output_dir)

    def test_extract_metadata(self):
        # We'll mock the internal _arun_extract_metadata to avoid network calls
        # But we want to test the parsing logic.
        # So we mock PlaywrightManager.smart_fetch to return a known HTML string.

        html_content = """
        <html>
            <head>
                <title>Test Page</title>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Organization",
                    "name": "Test Corp"
                }
                </script>
                <meta property="og:title" content="OpenGraph Title" />
                <meta name="description" content="Meta Description" />
            </head>
            <body></body>
        </html>
        """

        with patch(
            "web_scraper_toolkit.browser.playwright_handler.PlaywrightManager"
        ) as MockManager:
            instance = MockManager.return_value
            instance.start = AsyncMock()
            instance.stop = AsyncMock()
            # return content, url, status
            instance.smart_fetch = AsyncMock(
                return_value=(html_content, "https://example.com", 200)
            )

            output = extract_metadata("https://example.com")

            self.assertIn("METADATA REPORT", output)
            self.assertIn("Test Corp", output)
            self.assertIn("OpenGraph Title", output)
            self.assertIn("Meta Description", output)

    @patch("web_scraper_toolkit.browser.playwright_handler.PlaywrightManager")
    def test_capture_screenshot(self, MockManager):
        instance = MockManager.return_value
        instance.start = AsyncMock()
        instance.stop = AsyncMock()
        instance.capture_screenshot = AsyncMock(return_value=True)

        path = os.path.join(self.output_dir, "test.png")
        result = capture_screenshot("https://example.com", path)

        self.assertIn(f"Screenshot saved to {path}", result)
        instance.capture_screenshot.assert_called_once()
        args, kwargs = instance.capture_screenshot.call_args
        self.assertEqual(args[0], "https://example.com")
        self.assertEqual(args[1], path)
        self.assertTrue(kwargs.get("full_page", True))

    @patch("web_scraper_toolkit.browser.playwright_handler.PlaywrightManager")
    def test_save_as_pdf(self, MockManager):
        instance = MockManager.return_value
        instance.start = AsyncMock()
        instance.stop = AsyncMock()
        instance.save_pdf = AsyncMock(return_value=True)

        path = os.path.join(self.output_dir, "test.pdf")
        # PDF forces headless in the code
        result = save_as_pdf("https://example.com", path)

        self.assertIn(f"PDF saved to {path}", result)
        instance.save_pdf.assert_called_once()

        # Verify config update was passed to Manager constructor
        # We can't easily check constructor args on the mocked class instance creation
        # unless we check the CALL context of MockManager.
        # But for unit test, just verifying save_pdf is called is sufficient.


if __name__ == "__main__":
    unittest.main()
