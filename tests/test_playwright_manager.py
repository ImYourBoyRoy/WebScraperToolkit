# ./tests/test_playwright_manager.py
# ./tests/test_playwright_manager.py
"""
Unit tests for PlaywrightManager anti-bot behavior and profile gating.
Run with `python -m pytest -q tests/test_playwright_manager.py`.
Inputs: mocked Playwright objects and deterministic HTML/status fixtures.
Outputs: assertions over stealth profile behavior, retry policy, and block classification.
Side effects: clears local __pycache__ for fresh imports in each test setup.
"""

import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from web_scraper_toolkit.browser.config import BrowserConfig
from web_scraper_toolkit.browser._playwright_handler.page_ops import (
    DocumentDownloadTriggeredError,
)
from web_scraper_toolkit.browser.playwright_handler import (
    PlaywrightManager,
    classify_bot_block,
)


class TestPlaywrightManager(unittest.TestCase):
    def setUp(self) -> None:
        # Cache Scrub (Roy-Standard)
        import shutil

        cache_path = os.path.join(os.path.dirname(__file__), "__pycache__")
        if os.path.exists(cache_path):
            try:
                shutil.rmtree(cache_path)
            except Exception:
                pass
        profile_store_path = os.path.join(os.getcwd(), "host_profiles.json")
        if os.path.exists(profile_store_path):
            try:
                os.remove(profile_store_path)
            except Exception:
                pass

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self) -> None:
        self.loop.close()

    def test_initialization_defaults(self) -> None:
        config = BrowserConfig()
        pm = PlaywrightManager(config=config)
        self.assertEqual(pm.browser_type_name, "chromium")
        self.assertTrue(pm.headless)
        self.assertEqual(pm.stealth_profile, "baseline")
        self.assertNotIn(
            "--disable-site-isolation-trials",
            pm.launch_args,
        )

    def test_initialization_experimental_profile_adds_launch_flags(self) -> None:
        config = BrowserConfig(stealth_profile="experimental_serp")
        pm = PlaywrightManager(config)
        self.assertEqual(pm.stealth_profile, "experimental_serp")
        self.assertIn("--disable-site-isolation-trials", pm.launch_args)

    @patch("web_scraper_toolkit.browser.playwright_handler.async_playwright")
    def test_start_stop_logic(self, mock_playwright_fn: MagicMock) -> None:
        mock_playwright_obj = MagicMock()
        mock_browser_type = MagicMock()
        mock_browser = AsyncMock()

        mock_playwright_fn.return_value.start = AsyncMock(
            return_value=mock_playwright_obj
        )

        mock_playwright_obj.chromium = mock_browser_type
        mock_browser_type.launch = AsyncMock(return_value=mock_browser)
        mock_browser.is_connected = MagicMock(return_value=True)

        pm = PlaywrightManager({})
        self.loop.run_until_complete(pm.start())

        self.assertIsNotNone(pm._playwright)
        self.assertIsNotNone(pm._browser)
        mock_browser_type.launch.assert_called_once()

        mock_browser.close = AsyncMock()
        mock_playwright_obj.stop = AsyncMock()

        self.loop.run_until_complete(pm.stop())

        self.assertIsNone(pm._browser)
        self.assertIsNone(pm._playwright)
        mock_browser.close.assert_called_once()

    def test_proxy_settings_socks_ignores_auth(self) -> None:
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

    def test_proxy_settings_http_keeps_auth(self) -> None:
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

    def test_get_new_page_uses_async_route_handler(self) -> None:
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

        block_route = AsyncMock()
        block_route.request.url = "https://google-analytics.com/pixel"
        self.loop.run_until_complete(handler(block_route))
        block_route.abort.assert_awaited_once()

        normal_route = AsyncMock()
        normal_route.request.url = "https://example.com/page"
        self.loop.run_until_complete(handler(normal_route))
        normal_route.continue_.assert_awaited_once()

    def test_get_new_page_baseline_profile_keeps_static_viewport(self) -> None:
        pm = PlaywrightManager(BrowserConfig(stealth_profile="baseline"))
        pm.stealth_mode = False

        mock_browser = MagicMock()
        mock_browser.is_connected.return_value = True
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=AsyncMock())
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        pm._browser = mock_browser

        self.loop.run_until_complete(pm.get_new_page())
        kwargs = mock_browser.new_context.await_args.kwargs
        self.assertEqual(kwargs.get("viewport"), pm.default_viewport)
        self.assertNotIn("screen", kwargs)
        self.assertEqual(mock_context.add_cookies.await_count, 0)

    def test_get_new_page_applies_stealth_when_available(self) -> None:
        pm = PlaywrightManager(BrowserConfig(stealth_profile="baseline"))
        pm.stealth_mode = True

        mock_browser = MagicMock()
        mock_browser.is_connected.return_value = True
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        pm._browser = mock_browser
        pm._stealth = SimpleNamespace(apply_stealth_async=AsyncMock())

        self.loop.run_until_complete(pm.get_new_page())

        pm._stealth.apply_stealth_async.assert_awaited_once_with(mock_page)

    def test_get_new_page_experimental_profile_sets_screen_and_cookies(self) -> None:
        pm = PlaywrightManager(BrowserConfig(stealth_profile="experimental_serp"))
        pm.stealth_mode = False

        mock_browser = MagicMock()
        mock_browser.is_connected.return_value = True
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=AsyncMock())
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        pm._browser = mock_browser

        with patch(
            "web_scraper_toolkit.browser.playwright_handler.random.choice",
            return_value={"width": 1366, "height": 768},
        ):
            self.loop.run_until_complete(pm.get_new_page())

        kwargs = mock_browser.new_context.await_args.kwargs
        self.assertEqual(kwargs.get("viewport"), {"width": 1366, "height": 768})
        self.assertEqual(kwargs.get("screen"), {"width": 1366, "height": 768})
        self.assertGreaterEqual(mock_context.add_cookies.await_count, 1)

    def test_classify_bot_block_variants(self) -> None:
        self.assertEqual(
            classify_bot_block(
                status=200,
                final_url="https://www.google.com/sorry/index?continue=...",
                content_html="",
            ),
            "google_sorry",
        )
        self.assertEqual(
            classify_bot_block(
                status=429,
                final_url="https://www.google.com/search?q=test",
                content_html="Our systems have detected unusual traffic",
            ),
            "google_unusual_traffic",
        )
        self.assertEqual(
            classify_bot_block(
                status=202,
                final_url="https://html.duckduckgo.com/html/?q=test",
                content_html="Unfortunately, bots use DuckDuckGo too",
            ),
            "ddg_anomaly",
        )
        self.assertEqual(
            classify_bot_block(
                status=200,
                final_url="https://example.com",
                content_html="Just a moment...",
            ),
            "cf_challenge",
        )

    def test_fetch_page_content_propagates_cancelled_error(self) -> None:
        pm = PlaywrightManager(BrowserConfig())
        page = AsyncMock()
        page.goto = AsyncMock(side_effect=asyncio.CancelledError())

        async def _run() -> None:
            await pm.fetch_page_content(page=page, url="https://example.com")

        with self.assertRaises(asyncio.CancelledError):
            self.loop.run_until_complete(_run())

    def test_fetch_page_content_short_circuits_direct_document_url(self) -> None:
        pm = PlaywrightManager(BrowserConfig())
        page = AsyncMock()

        async def _run() -> None:
            await pm.fetch_page_content(
                page=page,
                url="https://pressrelease.com/files/example.docx",
            )

        with self.assertRaises(DocumentDownloadTriggeredError):
            self.loop.run_until_complete(_run())
        page.goto.assert_not_awaited()

    def test_fetch_page_content_raises_document_error_on_download_start(self) -> None:
        pm = PlaywrightManager(BrowserConfig())
        page = AsyncMock()
        page.goto = AsyncMock(
            side_effect=RuntimeError("Page.goto: Download is starting")
        )

        async def _run() -> None:
            await pm.fetch_page_content(page=page, url="https://example.com/report")

        with self.assertRaises(DocumentDownloadTriggeredError):
            self.loop.run_until_complete(_run())
        self.assertEqual(page.goto.await_count, 1)

    def test_smart_fetch_short_circuits_document_url_without_retry_matrix(self) -> None:
        pm = PlaywrightManager(
            BrowserConfig(
                native_fallback_policy="always",
            )
        )
        pm._smart_fetch_standard = AsyncMock(  # type: ignore[method-assign]
            return_value=("<html>should not run</html>", "https://example.com", 200)
        )
        pm._smart_fetch_native_fallback = AsyncMock(  # type: ignore[method-assign]
            return_value=("<html>should not run</html>", "https://example.com", 200)
        )

        content, final_url, status = self.loop.run_until_complete(
            pm.smart_fetch("https://pressrelease.com/files/example.docx")
        )

        self.assertIsNone(content)
        self.assertEqual(final_url, "https://pressrelease.com/files/example.docx")
        self.assertIsNone(status)
        pm._smart_fetch_standard.assert_not_awaited()
        pm._smart_fetch_native_fallback.assert_not_awaited()
        self.assertTrue(pm.get_last_fetch_metadata().get("download_detected"))

    def test_smart_fetch_allows_document_url_when_policy_is_allow_all(self) -> None:
        pm = PlaywrightManager(
            BrowserConfig(
                document_download_policy="allow_all",
                native_fallback_policy="off",
            )
        )
        pm._smart_fetch_standard = AsyncMock(  # type: ignore[method-assign]
            return_value=(None, "https://pressrelease.com/files/example.docx", None)
        )
        pm._smart_fetch_native_fallback = AsyncMock(  # type: ignore[method-assign]
            return_value=(None, "https://pressrelease.com/files/example.docx", None)
        )

        self.loop.run_until_complete(
            pm.smart_fetch("https://pressrelease.com/files/example.docx")
        )

        pm._smart_fetch_standard.assert_awaited_once()
        pm._smart_fetch_native_fallback.assert_not_awaited()

    def test_smart_fetch_download_triggered_allowed_policy_still_skips_retry_matrix(
        self,
    ) -> None:
        pm = PlaywrightManager(
            BrowserConfig(
                document_download_policy="allow_all",
                native_fallback_policy="always",
            )
        )
        pm._smart_fetch_standard = AsyncMock(  # type: ignore[method-assign]
            return_value=("<html>should not run</html>", "https://example.com", 200)
        )
        pm._smart_fetch_native_fallback = AsyncMock(  # type: ignore[method-assign]
            side_effect=DocumentDownloadTriggeredError(
                "https://pressrelease.com/files/example.docx",
                reason="download_started_allowed",
                policy_allows_download=True,
            )
        )

        content, final_url, status = self.loop.run_until_complete(
            pm.smart_fetch("https://pressrelease.com/files/example.docx")
        )

        self.assertIsNone(content)
        self.assertEqual(final_url, "https://pressrelease.com/files/example.docx")
        self.assertIsNone(status)
        pm._smart_fetch_standard.assert_not_awaited()
        pm._smart_fetch_native_fallback.assert_awaited_once()
        self.assertTrue(pm.get_last_fetch_metadata().get("download_policy_allowed"))

    def test_smart_fetch_honors_allow_headed_retry_false(self) -> None:
        pm = PlaywrightManager(
            BrowserConfig(
                headless=True,
                native_fallback_policy="off",
            )
        )

        page = AsyncMock()
        context = AsyncMock()
        pm.get_new_page = AsyncMock(return_value=(page, context))  # type: ignore[method-assign]
        pm.fetch_page_content = AsyncMock(  # type: ignore[method-assign]
            return_value=(
                "Our systems have detected unusual traffic",
                "https://example.com/challenge",
                429,
            )
        )
        pm.stop = AsyncMock()  # type: ignore[method-assign]
        pm.start = AsyncMock()  # type: ignore[method-assign]

        self.loop.run_until_complete(
            pm.smart_fetch(
                "https://example.com/search?q=test",
                allow_headed_retry=False,
            )
        )

        pm.fetch_page_content.assert_awaited_once()
        pm.stop.assert_not_awaited()
        pm.start.assert_not_awaited()

    def test_standard_flow_uses_native_only_retry_when_stealth_retry_still_blocked(
        self,
    ) -> None:
        pm = PlaywrightManager(
            BrowserConfig(
                headless=True,
                native_fallback_policy="off",
                stealth_mode=True,
            )
        )

        page1, page2, page3 = AsyncMock(), AsyncMock(), AsyncMock()
        ctx1, ctx2, ctx3 = AsyncMock(), AsyncMock(), AsyncMock()
        pm.get_new_page = AsyncMock(  # type: ignore[method-assign]
            side_effect=[(page1, ctx1), (page2, ctx2), (page3, ctx3)]
        )
        pm.fetch_page_content = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                (
                    "Our systems have detected unusual traffic",
                    "https://www.google.com/sorry/index",
                    429,
                ),
                ("blocked", "https://example.com/challenge", 403),
                ("<html>ok</html>", "https://example.com", 200),
            ]
        )
        pm.stop = AsyncMock()  # type: ignore[method-assign]
        pm.start = AsyncMock()  # type: ignore[method-assign]

        content, final_url, status = self.loop.run_until_complete(
            pm._smart_fetch_standard("https://example.com")
        )

        self.assertEqual(status, 200)
        self.assertEqual(final_url, "https://example.com")
        self.assertIn("ok", content or "")
        self.assertEqual(pm.fetch_page_content.await_count, 3)
        self.assertEqual(pm.get_new_page.await_count, 3)
        self.assertEqual(pm.stop.await_count, 2)
        self.assertEqual(pm.start.await_count, 2)
        self.assertTrue(pm.stealth_mode)  # restored after compatibility retry
        self.assertEqual(
            pm.get_last_fetch_metadata().get("attempt_profile"),
            "baseline_headed_no_stealth",
        )

    def test_standard_flow_cf_block_uses_native_only_headed_retry_immediately(
        self,
    ) -> None:
        pm = PlaywrightManager(
            BrowserConfig(
                headless=True,
                native_fallback_policy="off",
                stealth_mode=True,
            )
        )

        page1, page2 = AsyncMock(), AsyncMock()
        ctx1, ctx2 = AsyncMock(), AsyncMock()
        pm.get_new_page = AsyncMock(  # type: ignore[method-assign]
            side_effect=[(page1, ctx1), (page2, ctx2)]
        )
        pm.fetch_page_content = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                ("Just a moment", "https://example.com/challenge", 403),
                ("<html>ok</html>", "https://example.com", 200),
            ]
        )
        pm.stop = AsyncMock()  # type: ignore[method-assign]
        pm.start = AsyncMock()  # type: ignore[method-assign]

        content, final_url, status = self.loop.run_until_complete(
            pm._smart_fetch_standard("https://example.com")
        )

        self.assertEqual(status, 200)
        self.assertEqual(final_url, "https://example.com")
        self.assertIn("ok", content or "")
        self.assertEqual(pm.fetch_page_content.await_count, 2)
        second_call_kwargs = pm.fetch_page_content.await_args_list[1].kwargs
        self.assertEqual(
            second_call_kwargs.get("action_name"),
            "smart_retry_native_signals",
        )
        self.assertTrue(pm.stealth_mode)
        self.assertEqual(
            pm.get_last_fetch_metadata().get("attempt_profile"),
            "baseline_headed_no_stealth",
        )

    def test_serp_balanced_retry_order_native_headless_then_headed(self) -> None:
        pm = PlaywrightManager(
            BrowserConfig(
                serp_strategy="native_first",
                serp_retry_policy="balanced",
                serp_retry_backoff_seconds=0.0,
            )
        )
        pm._run_serp_native_attempt = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                (
                    "Our systems have detected unusual traffic",
                    "https://www.google.com/search?q=test",
                    429,
                    {"attempt_profile": "native_headless"},
                ),
                (
                    "<html><body>ok</body></html>",
                    "https://www.google.com/search?q=test",
                    200,
                    {"attempt_profile": "native_headed"},
                ),
            ]
        )
        pm._smart_fetch_standard = AsyncMock(  # type: ignore[method-assign]
            return_value=(None, "", None)
        )

        self.loop.run_until_complete(
            pm.smart_fetch(
                "https://www.google.com/search?q=test",
                provider="google_html",
                is_serp_request=True,
            )
        )

        self.assertEqual(pm._run_serp_native_attempt.await_count, 2)
        first_kwargs = pm._run_serp_native_attempt.await_args_list[0].kwargs
        second_kwargs = pm._run_serp_native_attempt.await_args_list[1].kwargs
        self.assertEqual(first_kwargs["attempt_profile"], "native_headless")
        self.assertTrue(bool(first_kwargs["headless"]))
        self.assertEqual(second_kwargs["attempt_profile"], "native_headed")
        self.assertFalse(bool(second_kwargs["headless"]))
        pm._smart_fetch_standard.assert_not_awaited()

    def test_serp_native_path_does_not_use_playwright_stealth(self) -> None:
        pm = PlaywrightManager(
            BrowserConfig(
                serp_strategy="native_first",
                serp_retry_policy="none",
                stealth_mode=True,
            )
        )
        pm._stealth = SimpleNamespace(apply_stealth_async=AsyncMock())
        pm._run_serp_native_attempt = AsyncMock(  # type: ignore[method-assign]
            return_value=(
                "<html><body>ok</body></html>",
                "https://www.google.com/search?q=test",
                200,
                {"attempt_profile": "native_headless"},
            )
        )

        self.loop.run_until_complete(
            pm.smart_fetch(
                "https://www.google.com/search?q=test",
                provider="google_html",
                is_serp_request=True,
            )
        )

        pm._stealth.apply_stealth_async.assert_not_awaited()
        self.assertEqual(pm._run_serp_native_attempt.await_count, 1)

    def test_non_serp_requests_still_use_standard_flow(self) -> None:
        pm = PlaywrightManager(
            BrowserConfig(
                serp_strategy="native_first",
                serp_retry_policy="balanced",
            )
        )
        pm._smart_fetch_standard = AsyncMock(  # type: ignore[method-assign]
            return_value=("ok", "https://example.com", 200)
        )
        pm._smart_fetch_serp_strategy = AsyncMock(  # type: ignore[method-assign]
            return_value=(None, "", None)
        )

        self.loop.run_until_complete(pm.smart_fetch("https://example.com"))

        pm._smart_fetch_standard.assert_awaited_once()
        pm._smart_fetch_serp_strategy.assert_not_awaited()

    def test_serp_allowlist_only_gates_native_strategy(self) -> None:
        pm = PlaywrightManager(
            BrowserConfig(
                serp_strategy="native_first",
                serp_allowlist_only=True,
            )
        )
        pm._smart_fetch_standard = AsyncMock(  # type: ignore[method-assign]
            return_value=("ok", "https://example.com", 200)
        )
        pm._smart_fetch_serp_strategy = AsyncMock(  # type: ignore[method-assign]
            return_value=(None, "", None)
        )

        self.loop.run_until_complete(
            pm.smart_fetch(
                "https://example.com/search?q=test",
                is_serp_request=True,
            )
        )
        pm._smart_fetch_standard.assert_awaited_once()
        pm._smart_fetch_serp_strategy.assert_not_awaited()

    def test_native_fallback_runs_when_primary_blocked(self) -> None:
        pm = PlaywrightManager(
            BrowserConfig(
                native_fallback_policy="on_blocked",
            )
        )
        pm._smart_fetch_standard = AsyncMock(  # type: ignore[method-assign]
            return_value=(
                "Access denied",
                "https://example.com/challenge",
                403,
            )
        )
        pm._smart_fetch_native_fallback = AsyncMock(  # type: ignore[method-assign]
            return_value=(
                "<html><body>ok</body></html>",
                "https://example.com/ok",
                200,
            )
        )

        content, final_url, status = self.loop.run_until_complete(
            pm.smart_fetch("https://example.com")
        )

        self.assertEqual(status, 200)
        self.assertEqual(final_url, "https://example.com/ok")
        self.assertIn("ok", content or "")
        pm._smart_fetch_standard.assert_awaited_once()
        pm._smart_fetch_native_fallback.assert_awaited_once()

    def test_smart_fetch_keeps_primary_metadata_when_native_fallback_loses(
        self,
    ) -> None:
        pm = PlaywrightManager(BrowserConfig(native_fallback_policy="on_blocked"))

        async def _primary(*args, **kwargs):
            pm._last_fetch_metadata = {
                "attempt_profile": "baseline_headless",
                "status": 200,
                "final_url": "https://example.com/article",
                "blocked_reason": "none",
            }
            return (
                "<html><main><article>real content "
                + ("word " * 400)
                + "</article></main></html>",
                "https://example.com/article",
                200,
            )

        async def _native(*args, **kwargs):
            pm._last_fetch_metadata = {
                "attempt_profile": "native_channel_chrome",
                "status": 403,
                "final_url": "https://example.com/challenge",
                "blocked_reason": "cf_challenge",
            }
            return "Just a moment", "https://example.com/challenge", 403

        pm._smart_fetch_standard = AsyncMock(side_effect=_primary)  # type: ignore[method-assign]
        pm._smart_fetch_native_fallback = AsyncMock(side_effect=_native)  # type: ignore[method-assign]
        pm._should_attempt_native_fallback = MagicMock(return_value=True)  # type: ignore[method-assign]

        content, final_url, status = self.loop.run_until_complete(
            pm.smart_fetch("https://example.com/article")
        )

        self.assertEqual(status, 200)
        self.assertEqual(final_url, "https://example.com/article")
        self.assertIn("real content", content or "")
        metadata = pm.get_last_fetch_metadata()
        self.assertEqual(metadata.get("attempt_profile"), "baseline_headless")
        self.assertEqual(metadata.get("status"), 200)
        self.assertEqual(metadata.get("selection_reason"), "primary_preferred")

    def test_native_fallback_disabled_policy_off(self) -> None:
        pm = PlaywrightManager(
            BrowserConfig(
                native_fallback_policy="off",
            )
        )
        pm._smart_fetch_standard = AsyncMock(  # type: ignore[method-assign]
            return_value=("blocked", "https://example.com/challenge", 403)
        )
        pm._smart_fetch_native_fallback = AsyncMock(  # type: ignore[method-assign]
            return_value=("ok", "https://example.com", 200)
        )

        self.loop.run_until_complete(pm.smart_fetch("https://example.com"))

        pm._smart_fetch_standard.assert_awaited_once()
        pm._smart_fetch_native_fallback.assert_not_awaited()

    def test_native_fallback_policy_always_short_circuits_primary(self) -> None:
        pm = PlaywrightManager(
            BrowserConfig(
                native_fallback_policy="always",
            )
        )
        pm._smart_fetch_standard = AsyncMock(  # type: ignore[method-assign]
            return_value=("primary", "https://example.com", 200)
        )
        pm._smart_fetch_native_fallback = AsyncMock(  # type: ignore[method-assign]
            return_value=("native", "https://example.com/native", 200)
        )

        content, _, _ = self.loop.run_until_complete(
            pm.smart_fetch("https://example.com")
        )

        self.assertEqual(content, "native")
        pm._smart_fetch_standard.assert_not_awaited()
        pm._smart_fetch_native_fallback.assert_awaited_once()

    def test_host_profile_can_enable_native_fallback_when_global_off(self) -> None:
        from web_scraper_toolkit.browser.host_profiles import HostProfileStore

        with tempfile.TemporaryDirectory() as tmp_dir:
            store_path = os.path.join(tmp_dir, "host_profiles.json")
            HostProfileStore(path=store_path).set_host_profile(
                "example.com",
                {
                    "native_fallback_policy": "on_blocked",
                    "native_browser_channels": ["chrome"],
                },
            )

            pm = PlaywrightManager(
                BrowserConfig(
                    native_fallback_policy="off",
                    host_profiles_path=store_path,
                )
            )
            pm._smart_fetch_standard = AsyncMock(  # type: ignore[method-assign]
                return_value=("blocked", "https://example.com/challenge", 403)
            )
            pm._smart_fetch_native_fallback = AsyncMock(  # type: ignore[method-assign]
                return_value=("ok", "https://example.com/ok", 200)
            )

            _, _, status = self.loop.run_until_complete(
                pm.smart_fetch("https://example.com")
            )
            self.assertEqual(status, 200)
            pm._smart_fetch_native_fallback.assert_awaited_once()

    def test_host_profile_can_start_headed_without_stealth(self) -> None:
        from web_scraper_toolkit.browser.host_profiles import HostProfileStore

        with tempfile.TemporaryDirectory() as tmp_dir:
            store_path = os.path.join(tmp_dir, "host_profiles.json")
            HostProfileStore(path=store_path).set_host_profile(
                "example.com",
                {
                    "headless": False,
                    "stealth_mode": False,
                    "native_fallback_policy": "off",
                },
            )

            pm = PlaywrightManager(
                BrowserConfig(
                    headless=True,
                    stealth_mode=True,
                    native_fallback_policy="off",
                    host_profiles_path=store_path,
                )
            )
            observed: dict[str, bool] = {}

            async def _fake_standard(*args, **kwargs):
                observed["headless"] = pm.headless
                observed["stealth_mode"] = pm.stealth_mode
                pm._last_fetch_metadata = {
                    "attempt_profile": "baseline_headed_no_stealth",
                    "stealth_engine": "native_only",
                    "status": 200,
                    "final_url": "https://example.com",
                    "blocked_reason": "none",
                }
                return "ok", "https://example.com", 200

            pm._smart_fetch_standard = AsyncMock(side_effect=_fake_standard)  # type: ignore[method-assign]

            _, _, status = self.loop.run_until_complete(
                pm.smart_fetch("https://example.com")
            )

            self.assertEqual(status, 200)
            self.assertFalse(observed["headless"])
            self.assertFalse(observed["stealth_mode"])
            self.assertTrue(pm.headless)
            self.assertTrue(pm.stealth_mode)

    def test_explicit_strategy_override_beats_host_profile(self) -> None:
        from web_scraper_toolkit.browser.host_profiles import HostProfileStore

        with tempfile.TemporaryDirectory() as tmp_dir:
            store_path = os.path.join(tmp_dir, "host_profiles.json")
            HostProfileStore(path=store_path).set_host_profile(
                "example.com",
                {
                    "native_fallback_policy": "on_blocked",
                    "native_browser_channels": ["chrome"],
                },
            )

            pm = PlaywrightManager(
                BrowserConfig(
                    native_fallback_policy="off",
                    host_profiles_path=store_path,
                )
            )
            pm._smart_fetch_standard = AsyncMock(  # type: ignore[method-assign]
                return_value=("blocked", "https://example.com/challenge", 403)
            )
            pm._smart_fetch_native_fallback = AsyncMock(  # type: ignore[method-assign]
                return_value=("ok", "https://example.com/ok", 200)
            )

            _, _, status = self.loop.run_until_complete(
                pm.smart_fetch(
                    "https://example.com",
                    strategy_overrides={"native_fallback_policy": "off"},
                )
            )
            self.assertEqual(status, 403)
            pm._smart_fetch_native_fallback.assert_not_awaited()

    def test_smart_fetch_metadata_includes_learning_flags(self) -> None:
        pm = PlaywrightManager(BrowserConfig(native_fallback_policy="off"))
        pm._smart_fetch_standard = AsyncMock(  # type: ignore[method-assign]
            return_value=("ok", "https://example.com", 200)
        )

        self.loop.run_until_complete(pm.smart_fetch("https://example.com"))

        metadata = pm.get_last_fetch_metadata()
        self.assertIn("context_mode", metadata)
        self.assertIn("had_persisted_state", metadata)
        self.assertIn("promotion_eligible", metadata)
        self.assertIn("run_id", metadata)
        self.assertIn("resolved_routing", metadata)
        self.assertEqual(metadata["context_mode"], "incognito")
        self.assertFalse(metadata["had_persisted_state"])
        self.assertTrue(metadata["promotion_eligible"])

    def test_learning_routing_promotes_native_channel_and_headed_baseline_hints(
        self,
    ) -> None:
        pm = PlaywrightManager(BrowserConfig(native_fallback_policy="on_blocked"))

        pm._last_fetch_metadata = {
            "attempt_profile": "native_channel_msedge",
            "stealth_engine": "native_channel",
            "native_headless": False,
            "native_context_mode": "persistent",
        }
        native_routing = pm._build_learning_routing()
        self.assertEqual(native_routing["native_fallback_policy"], "always")
        self.assertEqual(native_routing["native_browser_channels"][0], "msedge")
        self.assertFalse(native_routing["native_browser_headless"])
        self.assertEqual(native_routing["native_context_mode"], "persistent")

        pm._last_fetch_metadata = {
            "attempt_profile": "baseline_headed_no_stealth",
            "stealth_engine": "native_only",
        }
        baseline_routing = pm._build_learning_routing()
        self.assertFalse(baseline_routing["headless"])
        self.assertFalse(baseline_routing["stealth_mode"])

    def test_host_profiles_read_only_forces_apply_without_learning(self) -> None:
        pm = PlaywrightManager(
            BrowserConfig(
                host_profiles_enabled=False,
                host_profiles_read_only=True,
                host_learning_enabled=True,
            )
        )
        self.assertTrue(pm.host_profiles_enabled)
        self.assertTrue(pm.host_profiles_read_only)
        self.assertFalse(pm.host_learning_enabled)


if __name__ == "__main__":
    unittest.main()
