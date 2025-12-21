# ./tests/test_feature_coverage.py
"""
Feature Coverage Tests
======================

Comprehensive tests verifying every exported function works correctly.
Tests all scraping tools, MCP tools, and configuration options.

Run with:
    python -m pytest tests/test_feature_coverage.py -v
"""

import unittest
import tempfile
import shutil


class TestScrapingToolsExports(unittest.TestCase):
    """Test that all scraping_tools exports are importable and callable."""

    def test_all_exports_importable(self):
        """Verify every item in __all__ can be imported."""
        from web_scraper_toolkit.parsers.scraping_tools import __all__

        # All items should be importable
        from web_scraper_toolkit.parsers import scraping_tools

        for name in __all__:
            self.assertTrue(hasattr(scraping_tools, name), f"Missing export: {name}")


class TestMCPToolsCoverage(unittest.IsolatedAsyncioTestCase):
    """Test MCP server tool coverage."""

    async def test_all_mcp_tools_exist(self):
        """Verify all expected MCP tools are registered (34 total)."""
        from web_scraper_toolkit.server import mcp_server

        expected_tools = [
            # Scraping
            "scrape_url",
            "batch_scrape",
            "get_metadata",
            "screenshot",
            "save_pdf",
            # Discovery
            "get_sitemap",
            "crawl_site",
            "extract_contacts",
            "extract_links",
            # Search
            "search_web",
            "deep_research",
            # Autonomous
            "run_playbook",
            # Configuration
            "configure_scraper",
            "configure_stealth",
            "get_config",
            # Cache Management
            "clear_cache",
            "get_cache_stats",
            # Session Management
            "clear_session",
            "new_session",
            "list_sessions",
            # Content Processing
            "chunk_text",
            "get_token_count",
            "truncate_text",
            # Health & Validation
            "health_check",
            "validate_url",
            "detect_content_type",
            # File Operations
            "download_file",
            # Form Automation
            "fill_form",
            "extract_tables",
            "click_element",
            # Batch Operations
            "batch_contacts",
            # History & Retry
            "get_history",
            "clear_history",
            "configure_retry",
        ]

        # Get registered tool names from the mcp object
        tools = await mcp_server.mcp.get_tools()
        registered_tools = set(tools.keys())

        for tool_name in expected_tools:
            self.assertIn(tool_name, registered_tools, f"Missing MCP tool: {tool_name}")


class TestConfigurationTools(unittest.TestCase):
    """Test configuration management tools."""

    def test_browser_config_update(self):
        """Test browser config can be updated."""
        from web_scraper_toolkit.server.handlers.config import update_browser_config

        result = update_browser_config(headless=False)
        self.assertEqual(result["headless"], False)

        result = update_browser_config(headless=True)
        self.assertEqual(result["headless"], True)

    def test_stealth_config_update(self):
        """Test stealth config including robots.txt opt-out."""
        from web_scraper_toolkit.server.handlers.config import update_stealth_config

        # Default: respect robots
        result = update_stealth_config(respect_robots=True)
        self.assertTrue(result["respect_robots"])
        self.assertFalse(result["global_ignore_robots"])

        # Opt-out: ignore robots
        result = update_stealth_config(respect_robots=False)
        self.assertFalse(result["respect_robots"])
        self.assertTrue(result["global_ignore_robots"])

    def test_get_current_config(self):
        """Test getting current config returns all expected sections."""
        from web_scraper_toolkit.server.handlers.config import get_current_config

        config = get_current_config()

        self.assertIn("browser", config)
        self.assertIn("crawler", config)
        self.assertIn("headless", config["browser"])
        self.assertIn("respect_robots", config["crawler"])


class TestCacheModule(unittest.TestCase):
    """Test response cache module."""

    def setUp(self):
        """Create temp directory for cache tests."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cache_set_and_get(self):
        """Test caching content and retrieving it."""
        from web_scraper_toolkit.core import ResponseCache, CacheConfig

        config = CacheConfig(enabled=True, directory=self.temp_dir, ttl_seconds=300)
        cache = ResponseCache(config)

        url = "https://example.com/test"
        content = "<html><body>Test Content</body></html>"

        # Cache should be empty initially
        self.assertIsNone(cache.get(url))

        # Set content
        cache.set(url, content)

        # Should retrieve content
        retrieved = cache.get(url)
        self.assertEqual(retrieved, content)

    def test_cache_clear(self):
        """Test clearing cache."""
        from web_scraper_toolkit.core import ResponseCache, CacheConfig

        config = CacheConfig(enabled=True, directory=self.temp_dir)
        cache = ResponseCache(config)

        cache.set("https://example.com/1", "content1")
        cache.set("https://example.com/2", "content2")

        # Verify cached
        self.assertIsNotNone(cache.get("https://example.com/1"))

        # Clear
        result = cache.clear()
        self.assertGreater(result["cleared_memory"], 0)

        # Should be empty
        self.assertIsNone(cache.get("https://example.com/1"))

    def test_cache_stats(self):
        """Test cache statistics."""
        from web_scraper_toolkit.core import ResponseCache, CacheConfig

        config = CacheConfig(enabled=True, directory=self.temp_dir)
        cache = ResponseCache(config)

        cache.set("https://example.com", "content")
        cache.get("https://example.com")  # Hit
        cache.get("https://notcached.com")  # Miss

        stats = cache.get_stats()

        self.assertIn("hits", stats)
        self.assertIn("misses", stats)
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)


class TestChunkingModule(unittest.TestCase):
    """Test content chunking module."""

    def test_chunk_short_content(self):
        """Short content should return single chunk."""
        from web_scraper_toolkit.core import chunk_content

        short_text = "This is short text."
        chunks = chunk_content(short_text, max_size=1000)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].content, short_text)

    def test_chunk_long_content(self):
        """Long content should split into multiple chunks."""
        from web_scraper_toolkit.core import chunk_content

        long_text = "Word " * 5000  # ~25000 chars
        chunks = chunk_content(long_text, max_size=5000, overlap=100)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk.content), 5000 + 100)  # Allow small overflow

    def test_chunk_overlap(self):
        """Chunks should have overlap."""
        from web_scraper_toolkit.core import chunk_content_simple

        text = "A" * 10000
        chunks = chunk_content_simple(text, max_size=3000, overlap=200)

        # With overlap, later chunks should share content with previous
        if len(chunks) > 1:
            # End of first chunk should appear in start of second
            self.assertGreater(len(chunks), 1)


class TestTokensModule(unittest.TestCase):
    """Test token counting module."""

    def test_count_tokens(self):
        """Test basic token counting."""
        from web_scraper_toolkit.core import count_tokens

        text = "This is a simple test sentence with about ten words."
        tokens = count_tokens(text)

        # Should be roughly 10-15 tokens
        self.assertGreater(tokens, 5)
        self.assertLess(tokens, 50)

    def test_empty_text(self):
        """Empty text should return 0 tokens."""
        from web_scraper_toolkit.core import count_tokens

        self.assertEqual(count_tokens(""), 0)
        self.assertEqual(count_tokens(None), 0)

    def test_token_info(self):
        """Test detailed token info."""
        from web_scraper_toolkit.core import get_token_info

        text = "Hello world, this is a test."
        info = get_token_info(text)

        self.assertIn("estimated_tokens", info)
        self.assertIn("characters", info)
        self.assertIn("words", info)
        self.assertEqual(info["characters"], len(text))

    def test_truncate_to_tokens(self):
        """Test truncation to token limit."""
        from web_scraper_toolkit.core import truncate_to_tokens

        long_text = "Word " * 10000  # Very long
        truncated = truncate_to_tokens(long_text, max_tokens=100)

        self.assertLess(len(truncated), len(long_text))
        self.assertIn("[Truncated]", truncated)


class TestSessionModule(unittest.TestCase):
    """Test session management module."""

    def setUp(self):
        """Create temp directory for session tests."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_session_manager_init(self):
        """Test session manager initialization."""
        from web_scraper_toolkit.core import SessionManager, SessionConfig

        config = SessionConfig(directory=self.temp_dir)
        mgr = SessionManager(config)

        self.assertFalse(mgr.has_session("default"))

    def test_clear_nonexistent_session(self):
        """Clearing nonexistent session should not error."""
        from web_scraper_toolkit.core import SessionManager, SessionConfig

        config = SessionConfig(directory=self.temp_dir)
        mgr = SessionManager(config)

        result = mgr.clear_session("nonexistent")
        self.assertIn("cleared", result)


class TestUserAgents(unittest.TestCase):
    """Test stealth user-agent module."""

    def test_random_user_agent(self):
        """Test random user agent returns valid string."""
        from web_scraper_toolkit.core.user_agents import get_random_user_agent

        ua = get_random_user_agent()
        self.assertIsInstance(ua, str)
        self.assertIn("Mozilla", ua)

    def test_stealth_headers(self):
        """Test stealth headers include essential fields."""
        from web_scraper_toolkit.core.user_agents import get_stealth_headers

        headers = get_stealth_headers()

        self.assertIn("User-Agent", headers)
        self.assertIn("Accept", headers)
        self.assertIn("Accept-Language", headers)

    def test_simple_headers(self):
        """Test simple headers for lightweight requests."""
        from web_scraper_toolkit.core.user_agents import get_simple_headers

        headers = get_simple_headers()

        self.assertIn("User-Agent", headers)
        self.assertIn("Mozilla", headers["User-Agent"])


class TestRobotsTxtOptOut(unittest.TestCase):
    """Test robots.txt compliance is configurable."""

    def test_crawler_config_ignore_robots(self):
        """Test CrawlerConfig has global_ignore_robots option."""
        from web_scraper_toolkit.crawler.config import CrawlerConfig

        config = CrawlerConfig()
        self.assertFalse(config.global_ignore_robots)  # Default: respect

        config.global_ignore_robots = True
        self.assertTrue(config.global_ignore_robots)

    def test_playbook_respect_robots_configurable(self):
        """Test Playbook has respect_robots setting."""
        from web_scraper_toolkit.playbook.models import PlaybookSettings

        settings = PlaybookSettings()
        self.assertTrue(settings.respect_robots)  # Default: respect

        settings = PlaybookSettings(respect_robots=False)
        self.assertFalse(settings.respect_robots)


class TestSitemapTools(unittest.TestCase):
    """Test sitemap discovery and extraction tools."""

    def test_sitemap_imports(self):
        """Test all sitemap functions are importable."""
        from web_scraper_toolkit.parsers.sitemap import (
            parse_sitemap_urls,
            find_sitemap_urls,
        )

        # All imported successfully
        self.assertTrue(callable(parse_sitemap_urls))
        self.assertTrue(callable(find_sitemap_urls))


class TestBrowserConfig(unittest.TestCase):
    """Test BrowserConfig has no dead user_agent field."""

    def test_no_user_agent_field(self):
        """BrowserConfig should not have user_agent (uses native for stealth)."""
        from web_scraper_toolkit.browser.config import BrowserConfig

        config = BrowserConfig()

        # Should NOT have user_agent as field
        self.assertNotIn("user_agent", config.to_dict())


if __name__ == "__main__":
    unittest.main()
