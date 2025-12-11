import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os
import asyncio

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from web_scraper_toolkit.browser.playwright_handler import PlaywrightManager
from web_scraper_toolkit.core.config import ScraperConfig

class TestPlaywrightManager(unittest.TestCase):
    
    def setUp(self):
        # Cache Scrub (Roy-Standard)
        import shutil
        cache_path = os.path.join(os.path.dirname(__file__), '__pycache__')
        if os.path.exists(cache_path):
            try: shutil.rmtree(cache_path)
            except: pass
            
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def test_initialization_defaults(self):
        # Test default config
        config = ScraperConfig.load({})
        pm = PlaywrightManager(config=config)
        self.assertEqual(pm.browser_type_name, "chromium")
        # Default headless is now False (Visible) as per recent validaton
        self.assertFalse(pm.headless) 
        
    def test_initialization_custom(self):
        overrides = {
            "scraper_settings": {
                "browser_type": "firefox",
                "headless": True,
                "retry_attempts": 5
            }
        }
        config = ScraperConfig.load(overrides)
        pm = PlaywrightManager(config)
        self.assertEqual(pm.browser_type_name, "firefox")
        self.assertTrue(pm.headless)
        self.assertEqual(pm.default_action_retries, 5)

    @patch('web_scraper_toolkit.browser.playwright_handler.async_playwright')
    def test_start_stop_logic(self, mock_playwright_fn):
        # Mock the context manager of async_playwright
        mock_playwright_obj = MagicMock()
        mock_browser_type = MagicMock()
        mock_browser = AsyncMock()
        
        # Setup the chain: async_playwright().start() -> playwright_obj
        # Actually async_playwright() returns a ContextManager, but we use await in start() manually?
        # Re-reading code: "self._playwright = await async_playwright().start()"
        
        mock_playwright_fn.return_value.start = AsyncMock(return_value=mock_playwright_obj)
        
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

if __name__ == '__main__':
    unittest.main()
