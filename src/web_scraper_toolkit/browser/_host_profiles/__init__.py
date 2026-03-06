# ./src/web_scraper_toolkit/browser/_host_profiles/__init__.py
"""
Internal host-profile learning package split from the legacy monolithic module.
Used by `browser.host_profiles` facade to preserve public imports.
Run: imported by browser host profile APIs; no direct CLI entrypoint.
Inputs: host identifiers, routing payloads, and run telemetry metadata.
Outputs: normalized routing payloads and JSON-backed HostProfileStore behaviors.
Side effects: file I/O to host profile JSON paths via HostProfileStore.
Operational notes: this package is private; public consumers should use `browser.host_profiles`.
"""

from .constants import (
    DEFAULT_DEMOTION_THRESHOLD,
    DEFAULT_FALLBACK_POLICY,
    DEFAULT_PROMOTION_THRESHOLD,
    DEFAULT_SESSION_POLICY,
    DEFAULT_WINDOW_DAYS,
    MAX_AUDIT_EVENTS,
    MAX_SAMPLE_RUNS,
    MAX_SERP_BACKOFF_SECONDS,
    SAFE_NATIVE_CHANNELS,
    SAFE_NATIVE_FALLBACK_POLICIES,
    SAFE_SERP_RETRY_POLICIES,
    SAFE_SERP_STRATEGIES,
)
from .sanitizers import (
    _normalize_channel,
    _parse_iso,
    _utc_now_iso,
    sanitize_routing_profile,
)
from .store import HostProfileStore

__all__ = [
    "HostProfileStore",
    "_utc_now_iso",
    "_parse_iso",
    "_normalize_channel",
    "sanitize_routing_profile",
    "SAFE_SERP_STRATEGIES",
    "SAFE_SERP_RETRY_POLICIES",
    "SAFE_NATIVE_FALLBACK_POLICIES",
    "SAFE_NATIVE_CHANNELS",
    "DEFAULT_FALLBACK_POLICY",
    "DEFAULT_SESSION_POLICY",
    "DEFAULT_PROMOTION_THRESHOLD",
    "DEFAULT_DEMOTION_THRESHOLD",
    "DEFAULT_WINDOW_DAYS",
    "MAX_AUDIT_EVENTS",
    "MAX_SAMPLE_RUNS",
    "MAX_SERP_BACKOFF_SECONDS",
]
