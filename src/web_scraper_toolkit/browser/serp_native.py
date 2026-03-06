# ./src/web_scraper_toolkit/browser/serp_native.py
"""
SERP-native browser fingerprint helpers for Google/DDG requests.

Run via imports from `playwright_handler` (no standalone CLI entrypoint).
Inputs: target URL/provider, Playwright native user-agent string, and HTML/status outcomes.
Outputs: normalized SERP header hints, allowlist decisions, and block-state booleans.
Side effects: none; pure helper functions only.
Operational notes: keep heuristics conservative and scoped to SERP allowlisted domains.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

SearchProvider = Literal["google_html", "ddg_html"]

_GOOGLE_UNUSUAL_TRAFFIC_MARKERS = (
    "unusual traffic from your computer",
    "our systems have detected unusual traffic",
    "not a robot",
)

_DDG_ANOMALY_MARKERS = (
    "unfortunately, bots use duckduckgo too",
    "anomaly-modal",
    "cc=botnet",
    "challenge-submit",
)


def sanitize_headless_user_agent(native_ua: str) -> str:
    """Replace Playwright headless token while preserving Chromium version."""
    if not native_ua:
        return native_ua
    return native_ua.replace("HeadlessChrome", "Chrome")


def _extract_chrome_major_version(clean_ua: str) -> str:
    match = re.search(r"Chrome/(\d+)\.", clean_ua or "")
    return match.group(1) if match else "131"


def build_serp_client_hints(clean_ua: str) -> dict[str, str]:
    """Build conservative Client-Hints header set for SERP-native requests."""
    major_version = _extract_chrome_major_version(clean_ua)
    return {
        "Sec-Ch-Ua": (
            f'"Google Chrome";v="{major_version}", '
            f'"Not=A?Brand";v="8", '
            f'"Chromium";v="{major_version}"'
        ),
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Accept-Language": "en-US,en;q=0.9",
    }


def is_serp_allowlisted(url: str, provider: Optional[str]) -> bool:
    """Return True only for known SERP endpoints we intentionally patch."""
    normalized_provider = (provider or "").strip().lower()
    if normalized_provider in {"google_html", "ddg_html"}:
        return True

    lowered = (url or "").lower()
    google_match = "google.com/search" in lowered
    ddg_match = (
        "html.duckduckgo.com/html/" in lowered or "duckduckgo.com/html/" in lowered
    )
    return bool(google_match or ddg_match)


def is_serp_blocked(
    status: Optional[int],
    final_url: str,
    content: Optional[str],
) -> bool:
    """Conservative SERP block detector for Google/DDG bot challenges."""
    lowered = (content or "").lower()
    final = (final_url or "").lower()

    if "google.com/sorry" in final:
        return True
    if status in {403, 429} and "google." in final:
        return True
    if any(marker in lowered for marker in _GOOGLE_UNUSUAL_TRAFFIC_MARKERS):
        return True

    if status == 202 and "duckduckgo." in final:
        return True
    if any(marker in lowered for marker in _DDG_ANOMALY_MARKERS):
        return True
    return False
