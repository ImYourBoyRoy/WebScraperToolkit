# ./tests/test_px_solver.py
"""
PerimeterX Solver Unit Tests
==============================

Tests for the PerimeterX challenge solver module.
Validates imports, availability detection, and BotBlockReason classification
without requiring a live browser or pyautogui display.

Run: python -m pytest tests/test_px_solver.py -v
Inputs: None.
Outputs: pytest results.
Notes: Uses mocking to test behavior without pyautogui or Playwright.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, patch

import pytest

from web_scraper_toolkit.browser.playwright_handler import classify_bot_block


# ---------------------------------------------------------------------------
# classify_bot_block — PX detection
# ---------------------------------------------------------------------------


class TestClassifyBotBlockPX:
    """Verify classify_bot_block correctly flags PerimeterX challenges."""

    def test_px_captcha_marker(self) -> None:
        result = classify_bot_block(
            status=403,
            final_url="https://example.com/company",
            content_html='<div id="px-captcha">Loading...</div>',
        )
        assert result == "px_challenge"

    def test_press_and_hold_marker(self) -> None:
        result = classify_bot_block(
            status=200,
            final_url="https://example.com",
            content_html="<button>Press & Hold to confirm you are human</button>",
        )
        assert result == "px_challenge"

    def test_press_amp_hold_marker(self) -> None:
        result = classify_bot_block(
            status=200,
            final_url="https://example.com",
            content_html="<button>Press &amp; Hold</button>",
        )
        assert result == "px_challenge"

    def test_human_challenge_marker(self) -> None:
        result = classify_bot_block(
            status=200,
            final_url="https://example.com",
            content_html="<span>Human Challenge completed</span>",
        )
        assert result == "px_challenge"

    def test_perimeterx_marker(self) -> None:
        result = classify_bot_block(
            status=403,
            final_url="https://example.com",
            content_html='<script src="https://captcha.perimeterx.net/px.js"></script>',
        )
        assert result == "px_challenge"

    def test_clean_page_no_block(self) -> None:
        result = classify_bot_block(
            status=200,
            final_url="https://example.com/company",
            content_html="<html><body><h1>Example Company</h1></body></html>",
        )
        assert result == "none"

    def test_cf_challenge_still_detected(self) -> None:
        """Ensure CF challenge detection is NOT broken by PX additions."""
        result = classify_bot_block(
            status=403,
            final_url="https://example.com",
            content_html="<title>Just a moment</title><body>checking</body>",
        )
        assert result == "cf_challenge"

    def test_google_sorry_still_detected(self) -> None:
        """Ensure Google sorry detection is NOT broken by PX additions."""
        result = classify_bot_block(
            status=302,
            final_url="https://www.google.com/sorry/index",
            content_html="<html>Our systems have detected unusual traffic</html>",
        )
        assert result == "google_sorry"


# ---------------------------------------------------------------------------
# PerimeterXSolver — import and availability
# ---------------------------------------------------------------------------


class TestPerimeterXSolverImport:
    """Verify the solver module imports cleanly regardless of pyautogui."""

    def test_import_succeeds(self) -> None:
        """Module should import without error even if pyautogui is missing."""
        from web_scraper_toolkit.browser.px_solver import PerimeterXSolver

        assert hasattr(PerimeterXSolver, "is_available")
        assert hasattr(PerimeterXSolver, "solve_press_and_hold")
        assert hasattr(PerimeterXSolver, "solve_cloudflare_checkbox")

    def test_is_available_returns_bool(self) -> None:
        from web_scraper_toolkit.browser.px_solver import PerimeterXSolver

        result = PerimeterXSolver.is_available()
        assert isinstance(result, bool)

    def test_export_from_browser_package(self) -> None:
        """Verify PerimeterXSolver is accessible from browser package."""
        from web_scraper_toolkit.browser import PerimeterXSolver

        assert PerimeterXSolver is not None

    def test_is_available_false_when_pyautogui_missing(self) -> None:
        """Verify solver reports unavailable when pyautogui can't be imported."""
        import web_scraper_toolkit.browser.px_solver as px_mod

        # Reset cached state
        px_mod._pyautogui = None
        px_mod._pyautogui_available = None

        with patch.dict(sys.modules, {"pyautogui": None}):
            with patch("builtins.__import__", side_effect=ImportError("no pyautogui")):
                # Reset again after patching
                px_mod._pyautogui_available = None
                result = px_mod._ensure_pyautogui()

        # Restore for other tests
        px_mod._pyautogui_available = None
        assert result is False


# ---------------------------------------------------------------------------
# PerimeterXSolver — graceful degradation when headless
# ---------------------------------------------------------------------------


class TestPerimeterXSolverGraceful:
    """Verify solver returns False gracefully when it cannot act."""

    @pytest.mark.asyncio
    async def test_solve_returns_false_when_unavailable(self) -> None:
        """If pyautogui is unavailable, solve methods should return False."""
        import web_scraper_toolkit.browser.px_solver as px_mod

        original = px_mod._pyautogui_available
        px_mod._pyautogui_available = False

        try:
            mock_page = AsyncMock()
            result = await px_mod.PerimeterXSolver.solve_press_and_hold(mock_page)
            assert result is False

            result2 = await px_mod.PerimeterXSolver.solve_cloudflare_checkbox(mock_page)
            assert result2 is False
        finally:
            px_mod._pyautogui_available = original
