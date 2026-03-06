# ./tests/test_fetch_result_api.py
"""
Fetch-result API tests for structured markdown extraction metadata.
Run: `pytest tests/test_fetch_result_api.py -q`.
Inputs: fake Playwright manager instances and synthetic HTML payloads.
Outputs: assertions for markdown output and propagated routing metadata.
Side effects: none.
Operational notes: avoids launching a real browser by injecting a stub manager.
"""

from __future__ import annotations

import pytest

from web_scraper_toolkit.parsers.content import aread_website_markdown_result


class _FakeManager:
    async def smart_fetch(self, url: str):
        return "<html><body><h1>Acme</h1><p>Hello world.</p></body></html>", url, 200

    def get_last_fetch_metadata(self):
        return {
            "attempt_profile": "native_channel_chrome",
            "active_host_profile_applied": "zoominfo_profile",
            "blocked_reason": "none",
            "resolved_routing": {"strategy": "native"},
        }


@pytest.mark.asyncio
async def test_aread_website_markdown_result_returns_metadata() -> None:
    result = await aread_website_markdown_result(
        "https://example.com",
        playwright_manager=_FakeManager(),
    )
    assert result.status_code == 200
    assert result.route_selected == "native_channel_chrome"
    assert result.host_profile_applied == "zoominfo_profile"
    assert result.challenge_detected is False
    assert "Acme" in result.markdown
