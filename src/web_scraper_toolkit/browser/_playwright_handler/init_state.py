# ./src/web_scraper_toolkit/browser/_playwright_handler/init_state.py
"""
Initialize PlaywrightManager runtime state and proxy helper accessors.
Used by browser.playwright_handler facade via mixin composition.
Run: imported by facade only; no direct CLI entrypoint.
Inputs: BrowserConfig/dict payloads and optional proxy manager handle.
Outputs: configured PlaywrightManager instance attributes.
Side effects: may create HostProfileStore JSON file if enabled.
Operational notes: mirrors legacy initialization semantics.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, Literal, Mapping, Optional, Union, cast

from playwright.async_api import Browser, Playwright

from ..config import BrowserConfig
from ..host_profiles import HostProfileStore
from .constants import (
    BASELINE_LAUNCH_ARGS,
    DEFAULT_USER_AGENTS,
    EXPERIMENTAL_SERP_LAUNCH_ARGS,
)

if TYPE_CHECKING:
    from ...proxie.manager import ProxyManager

try:
    from playwright_stealth import Stealth as _StealthClass  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    _StealthClass = None

try:
    from playwright_stealth import stealth_async as _legacy_stealth_async  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    _legacy_stealth_async = None

logger = logging.getLogger("web_scraper_toolkit.browser.playwright_handler")
_STEALTH_BACKEND_LOGGED = False


class PlaywrightInitStateMixin:
    def __init__(
        self,
        config: Optional[Union[Dict[str, Any], BrowserConfig]] = None,
        proxy_manager: Optional["ProxyManager"] = None,
    ) -> None:
        if config is None:
            self.config = BrowserConfig()
        elif isinstance(config, BrowserConfig):
            self.config = config
        elif isinstance(config, dict):
            normalized_config: Dict[str, Any] = dict(config)
            nested_settings = normalized_config.get("scraper_settings")
            if isinstance(nested_settings, Mapping):
                merged_settings = dict(nested_settings)
                # Top-level explicit values override nested values.
                merged_settings.update(
                    {
                        key: value
                        for key, value in normalized_config.items()
                        if key != "scraper_settings"
                    }
                )
                normalized_config = merged_settings

            if (
                "timeout" not in normalized_config
                and "default_timeout_seconds" in normalized_config
            ):
                try:
                    normalized_config["timeout"] = int(
                        float(normalized_config["default_timeout_seconds"]) * 1000
                    )
                except Exception:
                    pass

            self.config = BrowserConfig.from_dict(normalized_config)
        else:
            logger.warning(
                "Invalid config type passed to PlaywrightManager: %s. Using default.",
                type(config),
            )
            self.config = BrowserConfig()

        self.browser_type_name = self.config.browser_type.lower()
        self.headless = self.config.headless
        self.stealth_mode = bool(getattr(self.config, "stealth_mode", True))

        raw_profile = str(
            getattr(self.config, "stealth_profile", "baseline") or "baseline"
        )
        normalized_profile = raw_profile.strip().lower()
        if normalized_profile not in {"baseline", "experimental_serp"}:
            logger.warning(
                "Invalid stealth_profile '%s'; defaulting to 'baseline'.", raw_profile
            )
            normalized_profile = "baseline"
        self.stealth_profile: Literal["baseline", "experimental_serp"] = cast(
            Literal["baseline", "experimental_serp"], normalized_profile
        )
        self._experimental_serp = self.stealth_profile == "experimental_serp"

        raw_serp_strategy = str(getattr(self.config, "serp_strategy", "none") or "none")
        normalized_serp_strategy = raw_serp_strategy.strip().lower()
        if normalized_serp_strategy not in {"none", "native_first", "baseline_first"}:
            logger.warning(
                "Invalid serp_strategy '%s'; defaulting to 'none'.",
                raw_serp_strategy,
            )
            normalized_serp_strategy = "none"
        self.serp_strategy: Literal["none", "native_first", "baseline_first"] = cast(
            Literal["none", "native_first", "baseline_first"],
            normalized_serp_strategy,
        )

        raw_retry_policy = str(
            getattr(self.config, "serp_retry_policy", "none") or "none"
        )
        normalized_retry_policy = raw_retry_policy.strip().lower()
        if normalized_retry_policy not in {"none", "balanced"}:
            logger.warning(
                "Invalid serp_retry_policy '%s'; defaulting to 'none'.",
                raw_retry_policy,
            )
            normalized_retry_policy = "none"
        self.serp_retry_policy: Literal["none", "balanced"] = cast(
            Literal["none", "balanced"],
            normalized_retry_policy,
        )
        self.serp_retry_backoff_seconds = max(
            0.0, float(getattr(self.config, "serp_retry_backoff_seconds", 12.0) or 12.0)
        )
        self.serp_allowlist_only = bool(
            getattr(self.config, "serp_allowlist_only", True)
        )
        self.serp_debug_capture_headers = bool(
            getattr(self.config, "serp_debug_capture_headers", False)
        )
        raw_native_policy = (
            str(
                getattr(self.config, "native_fallback_policy", "on_blocked")
                or "on_blocked"
            )
            .strip()
            .lower()
        )
        if raw_native_policy not in {"off", "on_blocked", "always"}:
            logger.warning(
                "Invalid native_fallback_policy '%s'; defaulting to 'on_blocked'.",
                raw_native_policy,
            )
            raw_native_policy = "on_blocked"
        self.native_fallback_policy: Literal["off", "on_blocked", "always"] = cast(
            Literal["off", "on_blocked", "always"],
            raw_native_policy,
        )

        raw_native_channels = tuple(
            str(channel).strip().lower()
            for channel in getattr(
                self.config, "native_browser_channels", ("chrome", "msedge")
            )
            if str(channel).strip()
        )
        if not raw_native_channels:
            raw_native_channels = ("chrome", "msedge")
        self.native_browser_channels = raw_native_channels
        self.native_browser_headless = bool(
            getattr(self.config, "native_browser_headless", False)
        )
        raw_native_context_mode = (
            str(getattr(self.config, "native_context_mode", "incognito") or "incognito")
            .strip()
            .lower()
        )
        if raw_native_context_mode not in {"incognito", "persistent"}:
            logger.warning(
                "Invalid native_context_mode '%s'; defaulting to 'incognito'.",
                raw_native_context_mode,
            )
            raw_native_context_mode = "incognito"
        self.native_context_mode: Literal["incognito", "persistent"] = cast(
            Literal["incognito", "persistent"],
            raw_native_context_mode,
        )
        self.native_profile_dir = str(
            getattr(self.config, "native_profile_dir", "") or ""
        ).strip()
        self.host_profiles_enabled = bool(
            getattr(self.config, "host_profiles_enabled", True)
        )
        self.host_profiles_path = str(
            getattr(self.config, "host_profiles_path", "./host_profiles.json")
            or "./host_profiles.json"
        ).strip()
        self.host_profiles_read_only = bool(
            getattr(self.config, "host_profiles_read_only", False)
        )
        self.host_learning_enabled = bool(
            getattr(self.config, "host_learning_enabled", True)
        )
        if self.host_profiles_read_only:
            # Read-only mode means: apply existing profiles, do not write learning updates.
            self.host_profiles_enabled = True
            self.host_learning_enabled = False
        raw_host_apply_mode = (
            str(
                getattr(self.config, "host_learning_apply_mode", "safe_subset")
                or "safe_subset"
            )
            .strip()
            .lower()
        )
        if raw_host_apply_mode not in {"safe_subset"}:
            logger.warning(
                "Invalid host_learning_apply_mode '%s'; defaulting to 'safe_subset'.",
                raw_host_apply_mode,
            )
            raw_host_apply_mode = "safe_subset"
        self.host_learning_apply_mode: Literal["safe_subset"] = cast(
            Literal["safe_subset"],
            raw_host_apply_mode,
        )
        try:
            host_learning_threshold = int(
                getattr(
                    self.config,
                    "host_learning_promotion_threshold",
                    2,
                )
                or 2
            )
        except Exception:
            host_learning_threshold = 2
        self.host_learning_promotion_threshold = max(1, host_learning_threshold)
        self._host_profile_store: Optional[HostProfileStore] = None
        self._host_profile_store_error: str = ""
        if self.host_profiles_enabled:
            try:
                self._host_profile_store = HostProfileStore(
                    path=self.host_profiles_path,
                    promotion_threshold=self.host_learning_promotion_threshold,
                    apply_mode=self.host_learning_apply_mode,
                    auto_create=True,
                )
            except Exception as exc:
                self._host_profile_store_error = str(exc)
                logger.warning(
                    "Unable to initialize HostProfileStore at '%s': %s",
                    self.host_profiles_path,
                    exc,
                )
                self._host_profile_store = None

        # Mapping properties
        self.user_agents = DEFAULT_USER_AGENTS
        launch_args = list(BASELINE_LAUNCH_ARGS)
        if self._experimental_serp:
            launch_args.extend(EXPERIMENTAL_SERP_LAUNCH_ARGS)
        # preserve order, remove duplicates
        self.launch_args = list(dict.fromkeys(launch_args))

        self.default_viewport = {
            "width": self.config.viewport_width,
            "height": self.config.viewport_height,
        }
        self.default_navigation_timeout_ms = self.config.timeout
        self.default_action_retries = 2
        self.proxy_manager = proxy_manager
        self._last_fetch_metadata: Dict[str, Any] = {}

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._browser_launch_fallback_used = False
        self._logged_socks_auth_skips: set[str] = set()
        self._stealth = _StealthClass() if _StealthClass is not None else None
        self._stealth_missing_warned = False
        global _STEALTH_BACKEND_LOGGED
        if not _STEALTH_BACKEND_LOGGED:
            if self._stealth is not None:
                logger.info("Playwright stealth backend: playwright_stealth.Stealth")
            elif callable(_legacy_stealth_async):
                logger.info(
                    "Playwright stealth backend: playwright_stealth.stealth_async"
                )
            else:
                logger.info(
                    "Playwright stealth backend: unavailable (basic webdriver scrub only)"
                )
            _STEALTH_BACKEND_LOGGED = True

        logger.info(
            "PlaywrightManager initialized: Browser=%s, Headless=%s, "
            "StealthProfile=%s, SerpStrategy=%s, NativeFallback=%s, "
            "NativeChannels=%s, NativeContextMode=%s, HostProfiles=%s, "
            "HostProfilesReadOnly=%s, HostLearning=%s(%s/%s), Default Timeout=%sms",
            self.browser_type_name,
            self.headless,
            self.stealth_profile,
            self.serp_strategy,
            self.native_fallback_policy,
            ",".join(self.native_browser_channels),
            self.native_context_mode,
            self.host_profiles_enabled,
            self.host_profiles_read_only,
            self.host_learning_enabled,
            self.host_learning_apply_mode,
            self.host_learning_promotion_threshold,
            self.default_navigation_timeout_ms,
        )

    def _build_playwright_proxy_settings(self, proxy_obj: Any) -> Dict[str, str]:
        """
        Build Playwright proxy settings from a Proxy model.
        NOTE: Playwright does not support SOCKS authentication fields.
        """
        protocol = (
            proxy_obj.protocol.value
            if hasattr(proxy_obj.protocol, "value")
            else str(proxy_obj.protocol)
        ).lower()
        proxy_settings: Dict[str, str] = {
            "server": f"{protocol}://{proxy_obj.hostname}:{proxy_obj.port}"
        }

        username = str(getattr(proxy_obj, "username", "") or "")
        password = str(getattr(proxy_obj, "password", "") or "")
        has_auth = bool(username or password)
        supports_auth = protocol in {"http", "https"}

        if supports_auth:
            if username:
                proxy_settings["username"] = username
            if password:
                proxy_settings["password"] = password
        elif has_auth:
            warning_key = f"{proxy_obj.hostname}:{proxy_obj.port}:{protocol}"
            if warning_key not in self._logged_socks_auth_skips:
                logger.warning(
                    "Proxy %s provided SOCKS credentials, but Playwright does not "
                    "support SOCKS authentication. Credentials will be ignored.",
                    warning_key,
                )
                self._logged_socks_auth_skips.add(warning_key)

        return proxy_settings

    def browser(self) -> Browser:
        """Expose active browser for backward-compatible advanced operations."""
        if self._browser is None or not self._browser.is_connected():
            raise RuntimeError("Browser is not started.")
        return self._browser

    def get_last_fetch_metadata(self) -> Dict[str, Any]:
        """Return metadata captured by the most recent smart_fetch call."""
        return dict(self._last_fetch_metadata)
