# ./src/web_scraper_toolkit/browser/_host_profiles/constants.py
"""
Shared constants for host-profile sanitization and learning decisions.
Used by internal host profile store/sanitizer modules.
Run: imported by host profile internals; not a standalone program.
Inputs: none.
Outputs: immutable routing-policy and telemetry window constants.
Side effects: none.
Operational notes: keep values synchronized with compatibility expectations.
"""

SAFE_SERP_STRATEGIES = {"none", "native_first", "baseline_first"}
SAFE_SERP_RETRY_POLICIES = {"none", "balanced"}
SAFE_NATIVE_FALLBACK_POLICIES = {"off", "on_blocked", "always"}
SAFE_NATIVE_CHANNELS = {"chrome", "msedge", "chromium"}
SAFE_CONTEXT_MODES = {"incognito", "persistent"}
SAFE_PROXY_POLICIES = {"direct_first", "proxy_first", "proxy_only", "direct_only"}
SAFE_PROXY_TIERS = {"", "socks5", "socks4", "http", "https"}

DEFAULT_FALLBACK_POLICY = "on_blocked"
DEFAULT_SESSION_POLICY = "incognito"
DEFAULT_PROMOTION_THRESHOLD = 2
DEFAULT_DEMOTION_THRESHOLD = 3
DEFAULT_WINDOW_DAYS = 7
MAX_AUDIT_EVENTS = 10
MAX_SAMPLE_RUNS = 20
MAX_SERP_BACKOFF_SECONDS = 180.0
