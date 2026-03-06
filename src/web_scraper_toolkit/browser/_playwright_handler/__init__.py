# ./src/web_scraper_toolkit/browser/_playwright_handler/__init__.py
"""
Private split modules for PlaywrightManager internals.
Used by browser.playwright_handler facade to preserve public imports.
Run: imported by browser facade only.
Inputs: browser config/state plus fetch/runtime parameters.
Outputs: mixin classes and shared constants for PlaywrightManager composition.
Side effects: none at import beyond symbol binding.
Operational notes: private package; consumers should use browser.playwright_handler.
"""

from .artifacts import PlaywrightSmartFetchArtifactsMixin
from .constants import (
    BASELINE_LAUNCH_ARGS,
    BotBlockReason,
    COMMON_VIEWPORTS,
    DEFAULT_USER_AGENTS,
    EXPERIMENTAL_SERP_LAUNCH_ARGS,
    NATIVE_FALLBACK_LAUNCH_ARGS,
    SERP_NATIVE_LAUNCH_ARGS,
    SerpProvider,
    WaitUntilState,
    _CF_CHALLENGE_MARKERS,
    _DDG_ANOMALY_MARKERS,
    _GOOGLE_UNUSUAL_TRAFFIC_MARKERS,
    _PX_CHALLENGE_MARKERS,
    classify_bot_block,
)
from .init_state import PlaywrightInitStateMixin
from .lifecycle import PlaywrightLifecycleMixin
from .native_attempts import PlaywrightNativeAttemptsMixin
from .page_ops import PlaywrightPageOpsMixin
from .routing import PlaywrightRoutingMixin
from .serp_attempts import PlaywrightSerpAttemptsMixin
from .strategy_support import PlaywrightStrategySupportMixin

__all__ = [
    "PlaywrightInitStateMixin",
    "PlaywrightRoutingMixin",
    "PlaywrightLifecycleMixin",
    "PlaywrightPageOpsMixin",
    "PlaywrightStrategySupportMixin",
    "PlaywrightNativeAttemptsMixin",
    "PlaywrightSerpAttemptsMixin",
    "PlaywrightSmartFetchArtifactsMixin",
    "WaitUntilState",
    "BotBlockReason",
    "SerpProvider",
    "classify_bot_block",
    "DEFAULT_USER_AGENTS",
    "COMMON_VIEWPORTS",
    "BASELINE_LAUNCH_ARGS",
    "EXPERIMENTAL_SERP_LAUNCH_ARGS",
    "SERP_NATIVE_LAUNCH_ARGS",
    "NATIVE_FALLBACK_LAUNCH_ARGS",
    "_GOOGLE_UNUSUAL_TRAFFIC_MARKERS",
    "_DDG_ANOMALY_MARKERS",
    "_CF_CHALLENGE_MARKERS",
    "_PX_CHALLENGE_MARKERS",
]
