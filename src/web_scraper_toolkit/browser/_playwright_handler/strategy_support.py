# ./src/web_scraper_toolkit/browser/_playwright_handler/strategy_support.py
"""
Strategy decision helpers for SERP routing and fallback gating.
Used by native/serp/smart-fetch mixins for shared condition logic.
Run: imported by facade class composition only.
Inputs: URL/provider/status/content and manager routing settings.
Outputs: booleans, normalized channel tuples, and block reason tuples.
Side effects: none.
Operational notes: pure helper methods to keep stateful flows concise.
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional, Tuple

from .constants import BotBlockReason, SerpProvider, classify_bot_block
from ..serp_native import is_serp_allowlisted


class PlaywrightStrategySupportMixin:
    def _should_use_serp_strategy(
        self,
        *,
        url: str,
        provider: Optional[SerpProvider],
        is_serp_request: bool,
    ) -> bool:
        if not is_serp_request:
            return False
        if self.serp_strategy == "none":
            return False
        if not self.serp_allowlist_only:
            return True
        return is_serp_allowlisted(url, provider)

    async def _capture_compact_js_fingerprint(self, page: Page) -> Dict[str, Any]:
        """Capture compact navigator snapshot for SERP debug telemetry."""
        try:
            data = await page.evaluate(
                """() => ({
                    userAgent: navigator.userAgent,
                    webdriver: navigator.webdriver,
                    platform: navigator.platform,
                    languages: navigator.languages,
                    hardwareConcurrency: navigator.hardwareConcurrency,
                    deviceMemory: navigator.deviceMemory,
                    maxTouchPoints: navigator.maxTouchPoints,
                    viewport: { width: window.innerWidth, height: window.innerHeight },
                })"""
            )
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _is_blocked_or_failed(
        self,
        *,
        status: Optional[int],
        final_url: str,
        content: Optional[str],
    ) -> Tuple[bool, BotBlockReason]:
        """Return tuple of (is_blocked_or_failed, block_reason)."""
        block_reason = classify_bot_block(
            status=status,
            final_url=final_url,
            content_html=content,
        )
        hard_failure = status is None or status in {403, 429, 503}
        empty_success = status == 200 and not content
        return bool(
            block_reason != "none" or hard_failure or empty_success
        ), block_reason

    def _should_attempt_native_fallback(
        self,
        *,
        status: Optional[int],
        final_url: str,
        content: Optional[str],
    ) -> bool:
        if self.native_fallback_policy == "off":
            return False
        if self.native_fallback_policy == "always":
            return True
        is_blocked, _ = self._is_blocked_or_failed(
            status=status,
            final_url=final_url,
            content=content,
        )
        return is_blocked

    def _normalized_native_channels(self) -> Tuple[str, ...]:
        alias_map = {
            "chrome": "chrome",
            "google chrome": "chrome",
            "google-chrome": "chrome",
            "edge": "msedge",
            "microsoft edge": "msedge",
            "microsoft-edge": "msedge",
            "msedge": "msedge",
            "chromium": "chromium",
        }
        channels: list[str] = []
        for raw_channel in self.native_browser_channels:
            normalized = alias_map.get(str(raw_channel).strip().lower())
            if normalized and normalized not in channels:
                channels.append(normalized)

        if not channels:
            channels = ["chrome", "msedge"]
        return tuple(channels)

    def _resolve_native_profile_dir(self, channel: str) -> Tuple[str, bool]:
        """
        Resolve profile directory for native persistent context.
        Returns: (path, should_cleanup_after_attempt)
        """
        if self.native_profile_dir:
            return self.native_profile_dir, False
        return tempfile.mkdtemp(prefix=f"wst_native_{channel}_"), True

