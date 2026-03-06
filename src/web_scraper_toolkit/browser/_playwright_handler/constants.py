# ./src/web_scraper_toolkit/browser/_playwright_handler/constants.py
"""
Shared constants and classifiers for PlaywrightManager split modules.
Run: imported by browser Playwright mixins and facade exports.
Inputs: status/url/html data for block classification helpers.
Outputs: normalized block reason enum values and runtime launch defaults.
Side effects: none.
Operational notes: keep names stable for backwards-compatible re-exports.
"""

from __future__ import annotations

from typing import Literal, Optional

DEFAULT_USER_AGENTS = [
    # We keep these for fallback, but we will default to 'None' (Native) for Cloudflare
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

# Common desktop resolutions — randomized per-context for optional experimental SERP profile.
COMMON_VIEWPORTS = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1920, "height": 1080},
    {"width": 1280, "height": 800},
    {"width": 1600, "height": 900},
]

BASELINE_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--enable-webgl",  # CRITICAL: Fixes 'No Adapter' error
    "--window-size=1400,1000",
    "--no-sandbox",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    # "--disable-gpu",            # Disabled: Conflicts with --enable-webgl for WebGL rendering
    "--ignore-certificate-errors",
]

EXPERIMENTAL_SERP_LAUNCH_ARGS = [
    "--disable-features=IsolateOrigins,site-per-process",
    "--disable-site-isolation-trials",
    "--disable-features=BlockInsecurePrivateNetworkRequests",
]

_GOOGLE_UNUSUAL_TRAFFIC_MARKERS = (
    "unusual traffic from your computer",
    "our systems have detected unusual traffic",
    "not a robot",
)

_DDG_ANOMALY_MARKERS = (
    "unfortunately, bots use duckduckgo too",
    "anomaly-modal",
    "cc=botnet",
    "select all squares containing a duck",
    "challenge-submit",
)

_CF_CHALLENGE_MARKERS = (
    "just a moment",
    "verification required",
    "attention required",
)

_PX_CHALLENGE_MARKERS = (
    "px-captcha",
    "perimeterx",
    "press & hold",
    "press &amp; hold",
    "human challenge",
)

WaitUntilState = Literal["commit", "domcontentloaded", "load", "networkidle"]
BotBlockReason = Literal[
    "google_sorry",
    "google_unusual_traffic",
    "ddg_anomaly",
    "cf_challenge",
    "px_challenge",
    "none",
]
SerpProvider = Literal["google_html", "ddg_html"]

SERP_NATIVE_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]

NATIVE_FALLBACK_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]


def classify_bot_block(
    *,
    status: Optional[int],
    final_url: str,
    content_html: Optional[str],
) -> BotBlockReason:
    """Classify known bot-block signatures into a small shared enum."""
    content = content_html or ""
    lowered = content.lower()
    final = (final_url or "").lower()

    if "google.com/sorry" in final or "sorry/index" in lowered:
        return "google_sorry"

    if any(marker in lowered for marker in _GOOGLE_UNUSUAL_TRAFFIC_MARKERS):
        return "google_unusual_traffic"

    if status in {403, 429} and "google." in final:
        return "google_unusual_traffic"

    if any(marker in lowered for marker in _DDG_ANOMALY_MARKERS):
        return "ddg_anomaly"

    if (
        any(marker in lowered for marker in _CF_CHALLENGE_MARKERS)
        and len(content) < 50000
    ):
        return "cf_challenge"

    if any(marker in lowered for marker in _PX_CHALLENGE_MARKERS):
        return "px_challenge"

    return "none"
