"""
Test MCP Server Module
======================

Tests for the modular MCP server architecture.
"""

import unittest


class TestMCPServer(unittest.IsolatedAsyncioTestCase):
    """Test MCP server initialization and tool registration."""

    async def test_server_loads(self):
        """Verify MCP server module loads without errors."""
        from web_scraper_toolkit.server import mcp_server

        self.assertIsNotNone(mcp_server.mcp)
        self.assertEqual(mcp_server.mcp.name, "Web Scraper Toolkit")

    async def test_tools_registered(self):
        """Verify all tool categories are registered."""
        from web_scraper_toolkit.server import mcp_server

        tools = await mcp_server.mcp.get_tools()
        tool_names = set(tools.keys())

        # Check for key tools from each category
        self.assertIn("scrape_url", tool_names)  # Scraping
        self.assertIn("get_sitemap", tool_names)  # Discovery
        self.assertIn("fill_form", tool_names)  # Forms
        self.assertIn("chunk_text", tool_names)  # Content
        self.assertIn("clear_cache", tool_names)  # Management
        self.assertIn("run_playbook", tool_names)  # Playbook

        # Verify count (should be ~33)
        self.assertGreaterEqual(len(tool_names), 30)

    async def test_envelope_format(self):
        """Verify response envelope format."""
        from web_scraper_toolkit.server.mcp_server import create_envelope
        import json

        result = create_envelope("success", {"key": "value"}, meta={"test": True})
        parsed = json.loads(result)

        self.assertEqual(parsed["status"], "success")
        self.assertEqual(parsed["data"]["key"], "value")
        self.assertIn("timestamp", parsed["meta"])
        self.assertTrue(parsed["meta"]["test"])

    async def test_error_format(self):
        """Verify error envelope format."""
        from web_scraper_toolkit.server.mcp_server import format_error
        import json

        result = format_error("test_func", ValueError("Test error"))
        parsed = json.loads(result)

        self.assertEqual(parsed["status"], "error")
        self.assertIn("test_func", parsed["data"])
        self.assertEqual(parsed["meta"]["error_type"], "ValueError")


class TestMCPToolModules(unittest.TestCase):
    """Test individual tool modules load correctly."""

    def test_scraping_module(self):
        """Verify scraping tools module is importable."""
        from web_scraper_toolkit.server.mcp_tools import register_scraping_tools

        self.assertTrue(callable(register_scraping_tools))

    def test_discovery_module(self):
        """Verify discovery tools module is importable."""
        from web_scraper_toolkit.server.mcp_tools import register_discovery_tools

        self.assertTrue(callable(register_discovery_tools))

    def test_forms_module(self):
        """Verify forms tools module is importable."""
        from web_scraper_toolkit.server.mcp_tools import register_form_tools

        self.assertTrue(callable(register_form_tools))

    def test_content_module(self):
        """Verify content tools module is importable."""
        from web_scraper_toolkit.server.mcp_tools import register_content_tools

        self.assertTrue(callable(register_content_tools))

    def test_management_module(self):
        """Verify management tools module is importable."""
        from web_scraper_toolkit.server.mcp_tools import register_management_tools

        self.assertTrue(callable(register_management_tools))


if __name__ == "__main__":
    unittest.main()
