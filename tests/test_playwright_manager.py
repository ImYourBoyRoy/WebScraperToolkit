import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import os
import asyncio
from types import SimpleNamespace

# Ensure src is in path
# sys.path handled by run_tests.py

from web_scraper_toolkit.browser.playwright_handler import PlaywrightManager
from web_scraper_toolkit.browser.config import BrowserConfig


class TestPlaywrightManager(unittest.TestCase):
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

    def test_initialization_defaults(self):
        # Test default config
        config = BrowserConfig()
        pm = PlaywrightManager(config=config)
        self.assertEqual(pm.browser_type_name, "chromium")
        # Default headless is now True (default in BrowserConfig)
        self.assertTrue(pm.headless)

    def test_initialization_custom(self):
        config = BrowserConfig(browser_type="firefox", headless=True)
        pm = PlaywrightManager(config)
        self.assertEqual(pm.browser_type_name, "firefox")
        self.assertTrue(pm.headless)
        # BrowserConfig doesn't have default_action_retries, removed assertion

    @patch("web_scraper_toolkit.browser.playwright_handler.async_playwright")
    def test_start_stop_logic(self, mock_playwright_fn):
        # Mock the context manager of async_playwright
        mock_playwright_obj = MagicMock()
        mock_browser_type = MagicMock()
        mock_browser = AsyncMock()

        # Setup the chain: async_playwright().start() -> playwright_obj
        # Actually async_playwright() returns a ContextManager, but we use await in start() manually?
        # Re-reading code: "self._playwright = await async_playwright().start()"

        mock_playwright_fn.return_value.start = AsyncMock(
            return_value=mock_playwright_obj
        )

        # Setup browser launcher
        mock_playwright_obj.chromium = mock_browser_type
        mock_browser_type.launch = AsyncMock(return_value=mock_browser)

        # FIX: is_connected() is a synchronous method in Playwright, so we must use MagicMock (not AsyncMock)
        mock_browser.is_connected = MagicMock(return_value=True)

        # Test Start
        pm = PlaywrightManager({})
        self.loop.run_until_complete(pm.start())

        self.assertIsNotNone(pm._playwright)
        self.assertIsNotNone(pm._browser)
        mock_browser_type.launch.assert_called_once()

        # Test Stop
        mock_browser.close = AsyncMock()
        mock_playwright_obj.stop = AsyncMock()

        self.loop.run_until_complete(pm.stop())

        self.assertIsNone(pm._browser)
        self.assertIsNone(pm._playwright)
        mock_browser.close.assert_called_once()

    def test_proxy_settings_socks_ignores_auth(self):
        pm = PlaywrightManager(BrowserConfig())
        proxy = SimpleNamespace(
            hostname="socks.example.com",
            port=1080,
            username="user",
            password="pass",
            protocol=SimpleNamespace(value="socks5"),
        )
        settings = pm._build_playwright_proxy_settings(proxy)
        self.assertEqual(settings["server"], "socks5://socks.example.com:1080")
        self.assertNotIn("username", settings)
        self.assertNotIn("password", settings)

    def test_proxy_settings_http_keeps_auth(self):
        pm = PlaywrightManager(BrowserConfig())
        proxy = SimpleNamespace(
            hostname="http.example.com",
            port=8080,
            username="user",
            password="pass",
            protocol=SimpleNamespace(value="http"),
        )
        settings = pm._build_playwright_proxy_settings(proxy)
        self.assertEqual(settings["server"], "http://http.example.com:8080")
        self.assertEqual(settings.get("username"), "user")
        self.assertEqual(settings.get("password"), "pass")

    def test_get_new_page_uses_async_route_handler(self):
        pm = PlaywrightManager(BrowserConfig())
        pm.stealth_mode = False

        mock_browser = MagicMock()
        mock_browser.is_connected.return_value = True
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        pm._browser = mock_browser

        page, context = self.loop.run_until_complete(pm.get_new_page())
        self.assertIs(page, mock_page)
        self.assertIs(context, mock_context)
        mock_context.route.assert_awaited_once()

        pattern, handler = mock_context.route.await_args.args
        self.assertEqual(pattern, "**/*")
        self.assertTrue(asyncio.iscoroutinefunction(handler))

        # Verify handler awaits abort/continue correctly
        block_route = AsyncMock()
        block_route.request.url = "https://google-analytics.com/pixel"
        self.loop.run_until_complete(handler(block_route))
        block_route.abort.assert_awaited_once()

        normal_route = AsyncMock()
        normal_route.request.url = "https://example.com/page"
        self.loop.run_until_complete(handler(normal_route))
        normal_route.continue_.assert_awaited_once()

    def test_fetch_page_content_propagates_cancelled_error(self):
        pm = PlaywrightManager(BrowserConfig())
        page = AsyncMock()
        page.goto = AsyncMock(side_effect=asyncio.CancelledError())

        async def _run() -> None:
            await pm.fetch_page_content(page=page, url="https://example.com")

        with self.assertRaises(asyncio.CancelledError):
            self.loop.run_until_complete(_run())


if __name__ == "__main__":
    unittest.main()
