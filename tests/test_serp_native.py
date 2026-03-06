# ./tests/test_serp_native.py
"""
Unit tests for SERP-native helper functions used by PlaywrightManager.
Run with `python -m pytest -q tests/test_serp_native.py`.
Inputs: deterministic URLs, status codes, and HTML markers.
Outputs: assertions over UA sanitization, client hints, allowlist matching, and block checks.
Side effects: none.
Operational notes: pure-function coverage only (no browser/network activity).
"""

from __future__ import annotations

from web_scraper_toolkit.browser.serp_native import (
    build_serp_client_hints,
    is_serp_allowlisted,
    is_serp_blocked,
    sanitize_headless_user_agent,
)


def test_sanitize_headless_user_agent_preserves_version() -> None:
    source = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) HeadlessChrome/145.0.7632.117 Safari/537.36"
    )
    cleaned = sanitize_headless_user_agent(source)
    assert "HeadlessChrome" not in cleaned
    assert "Chrome/145.0.7632.117" in cleaned


def test_build_serp_client_hints_contains_expected_keys() -> None:
    hints = build_serp_client_hints(
        "Mozilla/5.0 (...) Chrome/145.0.7632.117 Safari/537.36"
    )
    assert hints["Sec-Ch-Ua-Mobile"] == "?0"
    assert hints["Sec-Ch-Ua-Platform"] == '"Windows"'
    assert hints["Accept-Language"] == "en-US,en;q=0.9"
    assert 'Google Chrome";v="145' in hints["Sec-Ch-Ua"]


def test_is_serp_allowlisted_by_provider_or_url() -> None:
    assert is_serp_allowlisted("https://example.com", "google_html")
    assert is_serp_allowlisted("https://www.google.com/search?q=test", None)
    assert is_serp_allowlisted("https://html.duckduckgo.com/html/?q=test", None)
    assert not is_serp_allowlisted("https://example.com/about", None)


def test_is_serp_blocked_detects_common_markers() -> None:
    assert is_serp_blocked(
        200,
        "https://www.google.com/sorry/index?continue=...",
        "<html></html>",
    )
    assert is_serp_blocked(
        429,
        "https://www.google.com/search?q=test",
        "Our systems have detected unusual traffic",
    )
    assert is_serp_blocked(
        202,
        "https://html.duckduckgo.com/html/?q=test",
        "Unfortunately, bots use DuckDuckGo too",
    )
    assert not is_serp_blocked(
        200,
        "https://www.google.com/search?q=test",
        "<html><body>normal result page</body></html>",
    )
