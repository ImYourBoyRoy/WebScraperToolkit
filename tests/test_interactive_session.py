# ./tests/test_interactive_session.py
"""
Validate InteractiveSession LLM-control helpers for wait, keyboard, scroll, hover, and interaction maps.
Run: `python -m pytest tests/test_interactive_session.py -q`.
Inputs: unittest async mocks for Playwright page APIs and selector-driven control calls.
Outputs: assertions on method contracts, tool-state payloads, and guardrail validation errors.
Side effects: none; browser launch is bypassed via mocked `_ensure_browser`.
Operational notes: tests keep payloads small/deterministic and protect non-breaking session semantics.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from web_scraper_toolkit.server.handlers.interactive import InteractiveSession


class TestInteractiveSessionControls(unittest.IsolatedAsyncioTestCase):
    """Unit tests for high-value LLM control surface additions."""

    def _build_session(self) -> tuple[InteractiveSession, AsyncMock]:
        session = InteractiveSession()
        page = AsyncMock()
        page.url = "https://example.com/app"
        page.title = AsyncMock(return_value="Example App")
        page.wait_for_timeout = AsyncMock()
        session._page = page
        session._ensure_browser = AsyncMock(return_value=page)  # type: ignore[method-assign]
        return session, page

    async def test_wait_for_selector_state(self) -> None:
        session, page = self._build_session()
        page.wait_for_selector = AsyncMock()

        result = await session.wait_for(
            selector="#results", state="visible", timeout_ms=4200
        )

        page.wait_for_selector.assert_awaited_once_with(
            "#results",
            state="visible",
            timeout=4200,
        )
        self.assertEqual(result["wait"]["selector"], "#results")
        self.assertEqual(result["wait"]["state"], "visible")
        self.assertEqual(result["title"], "Example App")

    async def test_wait_for_invalid_state_raises(self) -> None:
        session, _ = self._build_session()

        with self.assertRaises(ValueError):
            await session.wait_for(
                selector="#results", state="eventually", timeout_ms=1000
            )

    async def test_press_key_focuses_selector(self) -> None:
        session, page = self._build_session()
        locator = AsyncMock()
        locator.first = locator
        locator.focus = AsyncMock()
        page.locator = MagicMock(return_value=locator)
        page.keyboard = SimpleNamespace(press=AsyncMock())

        result = await session.press_key(
            "Enter", selector="input[name='q']", delay_ms=50
        )

        locator.focus.assert_awaited_once_with(timeout=10000)
        page.keyboard.press.assert_awaited_once_with("Enter", delay=50)
        self.assertEqual(result["keyboard"]["key"], "Enter")
        self.assertEqual(result["keyboard"]["selector"], "input[name='q']")

    async def test_scroll_page_direction(self) -> None:
        session, page = self._build_session()
        page.evaluate = AsyncMock(return_value={"scrollX": 0, "scrollY": 1250})

        result = await session.scroll(direction="down", amount=1250, smooth=False)

        page.evaluate.assert_awaited_once()
        self.assertEqual(result["scroll"]["direction"], "down")
        self.assertEqual(result["scroll"]["amount"], 1250)
        self.assertEqual(result["scroll"]["position"]["scrollY"], 1250)

    async def test_hover_returns_state(self) -> None:
        session, page = self._build_session()
        page.hover = AsyncMock()

        result = await session.hover("nav .products")

        page.hover.assert_awaited_once_with("nav .products", timeout=10000)
        self.assertEqual(result["hover"]["selector"], "nav .products")

    async def test_interaction_map_payload(self) -> None:
        session, page = self._build_session()
        interaction_map = {
            "root_selector": "body",
            "count": 2,
            "truncated": False,
            "elements": [
                {
                    "index": 0,
                    "tag": "button",
                    "text": "Search",
                    "selector_hint": "#search",
                },
                {
                    "index": 1,
                    "tag": "a",
                    "text": "Pricing",
                    "selector_hint": "a[href='/pricing']",
                },
            ],
        }
        page.evaluate = AsyncMock(return_value=interaction_map)

        result = await session.get_interaction_map(max_elements=2)

        page.evaluate.assert_awaited_once()
        self.assertEqual(result["interaction_map"]["count"], 2)
        self.assertEqual(len(result["interaction_map"]["elements"]), 2)

    async def test_accessibility_tree_payload_is_trimmed(self) -> None:
        session, page = self._build_session()
        page.accessibility = SimpleNamespace(
            snapshot=AsyncMock(
                return_value={
                    "role": "document",
                    "name": "Example App Root",
                    "children": [
                        {"role": "button", "name": "Search"},
                        {"role": "link", "name": "Pricing"},
                    ],
                }
            )
        )

        result = await session.get_accessibility_tree(max_nodes=2, max_text_length=20)

        page.accessibility.snapshot.assert_awaited_once()
        self.assertEqual(result["accessibility_tree"]["node_count"], 2)
        self.assertTrue(result["accessibility_tree"]["truncated"])
        self.assertEqual(
            result["accessibility_tree"]["tree"]["role"],
            "document",
        )


if __name__ == "__main__":
    unittest.main()
