# ./src/web_scraper_toolkit/browser/config.py
"""
Browser Configuration
=====================

Typed browser config shared by CLI, MCP, crawler, and interactive browser flows.
Run: imported as a library module; not a direct CLI entry point.
Inputs: config dictionaries, CLI flags, and MCP configure_scraper updates.
Outputs: normalized BrowserConfig objects used by PlaywrightManager and interactive handlers.
Side effects: none (pure configuration helpers only).
Operational notes:
  - Defaults keep contexts incognito/ephemeral for safer local automation.
  - Native browser fallback is enabled on blocked responses by default.
  - We still avoid hardcoded custom UA by default to preserve native browser signals.
"""

from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping, Tuple

NativeFallbackPolicy = Literal["off", "on_blocked", "always"]
BrowserContextMode = Literal["incognito", "persistent"]
BrowserChannel = Literal["chromium", "chrome", "msedge"]
HostLearningApplyMode = Literal["safe_subset"]
DocumentDownloadPolicy = Literal["disallow", "allowlist", "allow_all"]


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_channel(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    alias_map = {
        "google-chrome": "chrome",
        "google chrome": "chrome",
        "chrome": "chrome",
        "edge": "msedge",
        "microsoft edge": "msedge",
        "microsoft-edge": "msedge",
        "msedge": "msedge",
        "chromium": "chromium",
    }
    return alias_map.get(text, "")


def _normalize_channel_list(value: Any, fallback: Tuple[str, ...]) -> Tuple[str, ...]:
    if isinstance(value, str):
        raw_items = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw_items = [str(part).strip() for part in value]
    else:
        raw_items = []

    channels: list[str] = []
    for raw in raw_items:
        normalized = _normalize_channel(raw)
        if normalized and normalized not in channels:
            channels.append(normalized)

    if not channels:
        return fallback
    return tuple(channels)


def _normalize_policy(
    value: Any, default: NativeFallbackPolicy
) -> NativeFallbackPolicy:
    text = str(value or "").strip().lower()
    alias_map = {
        "off": "off",
        "none": "off",
        "disabled": "off",
        "disable": "off",
        "on_blocked": "on_blocked",
        "blocked": "on_blocked",
        "auto": "on_blocked",
        "fallback": "on_blocked",
        "always": "always",
    }
    normalized = alias_map.get(text, default)
    return normalized  # type: ignore[return-value]


def _normalize_document_download_policy(
    value: Any,
    default: DocumentDownloadPolicy,
) -> DocumentDownloadPolicy:
    text = str(value or "").strip().lower()
    alias_map = {
        "disallow": "disallow",
        "block": "disallow",
        "deny": "disallow",
        "disabled": "disallow",
        "allowlist": "allowlist",
        "whitelist": "allowlist",
        "allow_all": "allow_all",
        "allow": "allow_all",
        "enabled": "allow_all",
    }
    normalized = alias_map.get(text, default)
    return normalized  # type: ignore[return-value]


def _normalize_context_mode(
    value: Any, default: BrowserContextMode
) -> BrowserContextMode:
    text = str(value or "").strip().lower()
    if text in {"persistent", "profile", "stateful"}:
        return "persistent"
    if text in {"incognito", "ephemeral", "temporary", "temp"}:
        return "incognito"
    return default


def _normalize_string_tuple(value: Any, fallback: Tuple[str, ...]) -> Tuple[str, ...]:
    if isinstance(value, str):
        raw_items = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw_items = [str(part).strip() for part in value]
    else:
        raw_items = []

    normalized: list[str] = []
    for raw in raw_items:
        lowered = raw.lower()
        if lowered and lowered not in normalized:
            normalized.append(lowered)

    if not normalized:
        return fallback
    return tuple(normalized)


@dataclass
class BrowserConfig:
    headless: bool = True
    browser_type: str = "chromium"
    stealth_mode: bool = True
    stealth_profile: Literal["baseline", "experimental_serp"] = "baseline"
    serp_strategy: Literal["none", "native_first", "baseline_first"] = "none"
    serp_retry_policy: Literal["none", "balanced"] = "none"
    serp_retry_backoff_seconds: float = 12.0
    serp_allowlist_only: bool = True
    serp_debug_capture_headers: bool = False
    viewport_width: int = 1280
    viewport_height: int = 800
    timeout: int = 30000
    native_fallback_policy: NativeFallbackPolicy = "on_blocked"
    native_browser_channels: Tuple[str, ...] = ("chrome", "msedge")
    native_browser_headless: bool = False
    native_context_mode: BrowserContextMode = "incognito"
    native_profile_dir: str = ""
    interactive_channel: BrowserChannel = "chrome"
    interactive_context_mode: BrowserContextMode = "incognito"
    interactive_profile_dir: str = ""
    host_profiles_enabled: bool = True
    host_profiles_path: str = "./host_profiles.json"
    host_profiles_read_only: bool = False
    host_learning_enabled: bool = True
    host_learning_apply_mode: HostLearningApplyMode = "safe_subset"
    host_learning_promotion_threshold: int = 2
    proxy_aware_learning: bool = False
    proxy_tier: str = ""
    document_download_policy: DocumentDownloadPolicy = "disallow"
    document_download_allowed_domains: Tuple[str, ...] = ()
    document_download_blocked_domains: Tuple[str, ...] = ()
    document_download_extensions: Tuple[str, ...] = (
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".xlsm",
        ".ppt",
        ".pptx",
        ".pptm",
        ".csv",
        ".rtf",
        ".odt",
        ".ods",
        ".odp",
        ".zip",
        ".7z",
        ".rar",
    )
    # Note: No user_agent field - Playwright uses native UA for stealth

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> "BrowserConfig":
        data = dict(raw or {})

        stealth_profile = str(data.get("stealth_profile", "baseline")).strip().lower()
        if stealth_profile not in {"baseline", "experimental_serp"}:
            stealth_profile = "baseline"

        serp_strategy = str(data.get("serp_strategy", "none")).strip().lower()
        if serp_strategy not in {"none", "native_first", "baseline_first"}:
            serp_strategy = "none"

        serp_retry_policy = str(data.get("serp_retry_policy", "none")).strip().lower()
        if serp_retry_policy not in {"none", "balanced"}:
            serp_retry_policy = "none"

        host_learning_apply_mode = (
            str(data.get("host_learning_apply_mode", "safe_subset")).strip().lower()
        )
        if host_learning_apply_mode not in {"safe_subset"}:
            host_learning_apply_mode = "safe_subset"

        interactive_channel = _normalize_channel(data.get("interactive_channel"))
        if interactive_channel not in {"chromium", "chrome", "msedge"}:
            interactive_channel = "chrome"

        try:
            host_learning_threshold = int(
                data.get("host_learning_promotion_threshold", 2)
            )
        except Exception:
            host_learning_threshold = 2

        return cls(
            headless=_as_bool(data.get("headless", True), True),
            browser_type=str(data.get("browser_type", "chromium")),
            stealth_mode=_as_bool(data.get("stealth_mode", True), True),
            stealth_profile=stealth_profile,  # type: ignore[arg-type]
            serp_strategy=serp_strategy,  # type: ignore[arg-type]
            serp_retry_policy=serp_retry_policy,  # type: ignore[arg-type]
            serp_retry_backoff_seconds=float(
                data.get("serp_retry_backoff_seconds", 12.0)
            ),
            serp_allowlist_only=_as_bool(data.get("serp_allowlist_only", True), True),
            serp_debug_capture_headers=_as_bool(
                data.get("serp_debug_capture_headers", False),
                False,
            ),
            viewport_width=int(data.get("viewport_width", 1280)),
            viewport_height=int(data.get("viewport_height", 800)),
            timeout=int(data.get("timeout", 30000)),
            native_fallback_policy=_normalize_policy(
                data.get("native_fallback_policy"),
                "on_blocked",
            ),
            native_browser_channels=_normalize_channel_list(
                data.get("native_browser_channels"),
                ("chrome", "msedge"),
            ),
            native_browser_headless=_as_bool(
                data.get("native_browser_headless", False),
                False,
            ),
            native_context_mode=_normalize_context_mode(
                data.get("native_context_mode"),
                "incognito",
            ),
            native_profile_dir=str(data.get("native_profile_dir", "") or "").strip(),
            interactive_channel=interactive_channel,  # type: ignore[arg-type]
            interactive_context_mode=_normalize_context_mode(
                data.get("interactive_context_mode"),
                "incognito",
            ),
            interactive_profile_dir=str(
                data.get("interactive_profile_dir", "") or ""
            ).strip(),
            host_profiles_enabled=_as_bool(
                data.get("host_profiles_enabled", True),
                True,
            ),
            host_profiles_path=str(
                data.get("host_profiles_path", "./host_profiles.json")
                or "./host_profiles.json"
            ).strip(),
            host_profiles_read_only=_as_bool(
                data.get("host_profiles_read_only", False),
                False,
            ),
            host_learning_enabled=_as_bool(
                data.get("host_learning_enabled", True),
                True,
            ),
            host_learning_apply_mode=host_learning_apply_mode,  # type: ignore[arg-type]
            host_learning_promotion_threshold=max(
                1,
                host_learning_threshold,
            ),
            proxy_aware_learning=_as_bool(
                data.get("proxy_aware_learning", False),
                False,
            ),
            proxy_tier=str(data.get("proxy_tier", "") or "").strip().lower(),
            document_download_policy=_normalize_document_download_policy(
                data.get("document_download_policy"),
                "disallow",
            ),
            document_download_allowed_domains=_normalize_string_tuple(
                data.get("document_download_allowed_domains"),
                (),
            ),
            document_download_blocked_domains=_normalize_string_tuple(
                data.get("document_download_blocked_domains"),
                (),
            ),
            document_download_extensions=_normalize_string_tuple(
                data.get("document_download_extensions"),
                (
                    ".doc",
                    ".docx",
                    ".xls",
                    ".xlsx",
                    ".xlsm",
                    ".ppt",
                    ".pptx",
                    ".pptm",
                    ".csv",
                    ".rtf",
                    ".odt",
                    ".ods",
                    ".odp",
                    ".zip",
                    ".7z",
                    ".rar",
                ),
            ),
        )

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["native_browser_channels"] = list(self.native_browser_channels)
        return payload
