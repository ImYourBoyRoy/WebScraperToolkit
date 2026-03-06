# ./src/web_scraper_toolkit/browser/_host_profiles/sanitizers.py
"""
Normalization utilities for host-profile routing payloads and timestamps.
Used by HostProfileStore and public host profile facade exports.
Run: imported by host profile internals; no CLI entrypoint.
Inputs: raw routing mappings and optional timestamp/channel values.
Outputs: safe, normalized routing dictionaries and parsed UTC datetimes.
Side effects: none.
Operational notes: only safe-subset fields survive normalization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from .constants import (
    MAX_SERP_BACKOFF_SECONDS,
    SAFE_NATIVE_CHANNELS,
    SAFE_NATIVE_FALLBACK_POLICIES,
    SAFE_SERP_RETRY_POLICIES,
    SAFE_SERP_STRATEGIES,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_channel(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    alias_map = {
        "chrome": "chrome",
        "google chrome": "chrome",
        "google-chrome": "chrome",
        "msedge": "msedge",
        "edge": "msedge",
        "microsoft edge": "msedge",
        "microsoft-edge": "msedge",
        "chromium": "chromium",
    }
    normalized = alias_map.get(text, "")
    if normalized in SAFE_NATIVE_CHANNELS:
        return normalized
    return ""


def sanitize_routing_profile(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Keep only auto-learn safe subset routing fields and normalize values.
    """
    clean: Dict[str, Any] = {}

    fallback_policy = (
        str(payload.get("native_fallback_policy", "") or "").strip().lower()
    )
    if fallback_policy in SAFE_NATIVE_FALLBACK_POLICIES:
        clean["native_fallback_policy"] = fallback_policy

    channel_raw = payload.get("native_browser_channels")
    channel_values: list[str] = []
    if isinstance(channel_raw, str):
        channel_values = [part.strip() for part in channel_raw.split(",")]
    elif isinstance(channel_raw, (list, tuple, set)):
        channel_values = [str(part).strip() for part in channel_raw]
    channels: list[str] = []
    for raw in channel_values:
        normalized = _normalize_channel(raw)
        if normalized and normalized not in channels:
            channels.append(normalized)
    if channels:
        clean["native_browser_channels"] = channels

    if "allow_headed_retry" in payload:
        clean["allow_headed_retry"] = bool(payload.get("allow_headed_retry"))

    serp_strategy = str(payload.get("serp_strategy", "") or "").strip().lower()
    if serp_strategy in SAFE_SERP_STRATEGIES:
        clean["serp_strategy"] = serp_strategy

    serp_retry_policy = str(payload.get("serp_retry_policy", "") or "").strip().lower()
    if serp_retry_policy in SAFE_SERP_RETRY_POLICIES:
        clean["serp_retry_policy"] = serp_retry_policy

    if "serp_retry_backoff_seconds" in payload:
        try:
            backoff = float(payload.get("serp_retry_backoff_seconds", 0.0))
        except Exception:
            backoff = 0.0
        clean["serp_retry_backoff_seconds"] = max(
            0.0, min(MAX_SERP_BACKOFF_SECONDS, backoff)
        )

    return clean
