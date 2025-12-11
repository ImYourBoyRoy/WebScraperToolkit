import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import asyncio

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

# --- MOCK SETUP START ---
# We must mock fastmcp BEFORE importing mcp_server
sys.modules["fastmcp"] = MagicMock()


# Define the identity decorator
def identity_decorator(*args, **kwargs):
    def wrapper(func):
        return func

    return wrapper


# Configure the mock to return this decorator when @mcp.tool() is called
# FastMCP("name") returns an instance. That instance.tool() is the decorator.
mock_mcp_instance = sys.modules["fastmcp"].FastMCP.return_value
mock_mcp_instance.tool.side_effect = identity_decorator

# --- MOCK SETUP END ---

# Mock the underlying tools so imports don't fail or do weird things
with (
    patch("web_scraper_toolkit.server.mcp_server.read_website_markdown"),
    patch("web_scraper_toolkit.server.mcp_server.read_website_content"),
    patch("web_scraper_toolkit.server.mcp_server.general_web_search"),
    patch("web_scraper_toolkit.server.mcp_server.get_sitemap_urls"),
    patch("web_scraper_toolkit.server.mcp_server.capture_screenshot"),
):
    from web_scraper_toolkit.server import mcp_server


class TestMCPServer(unittest.TestCase):
    def setUp(self):
        # Cache Scrub
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

    def test_server_initialization(self):
        # Verify FastMCP was instantiated with correct name
        self.assertTrue(mcp_server.mcp)
        sys.modules["fastmcp"].FastMCP.assert_called_with("WebScraperToolkit")

    @patch("web_scraper_toolkit.server.mcp_server.run_in_process")
    def test_tool_methods_call_wrapper(self, mock_run):
        """
        Since we mocked the decorator to be identity, calling scrape_url(...)
        calls the actual async function defined in mcp_server.py.
        That function calls `run_in_process`. We mock `run_in_process`
        to verify it's called with the correct internal function.
        """
        mock_run.return_value = "Mocked Result"

        # 1. Scrape URL
        res = self.loop.run_until_complete(mcp_server.scrape_url("https://example.com"))
        self.assertEqual(res, "Mocked Result")
        # Verify it called run_in_process w/ read_website_markdown
        args, _ = mock_run.call_args
        # args[0] is the function passed to run_in_process
        self.assertEqual(args[0].__name__, "read_website_markdown")
        self.assertEqual(args[1], "https://example.com")

        # 2. Search
        res = self.loop.run_until_complete(mcp_server.search_web("query"))
        args, _ = mock_run.call_args
        self.assertEqual(args[0].__name__, "general_web_search")

        # 3. Sitemap
        res = self.loop.run_until_complete(
            mcp_server.get_sitemap("https://example.com")
        )
        args, _ = mock_run.call_args
        self.assertEqual(args[0].__name__, "get_sitemap_urls")

        # 4. Screenshot
        res = self.loop.run_until_complete(
            mcp_server.screenshot("https://example.com", "path.png")
        )
        args, _ = mock_run.call_args
        self.assertEqual(args[0].__name__, "capture_screenshot")


if __name__ == "__main__":
    unittest.main()
