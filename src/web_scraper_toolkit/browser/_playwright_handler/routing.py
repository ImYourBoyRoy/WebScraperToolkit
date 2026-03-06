# ./src/web_scraper_toolkit/browser/_playwright_handler/routing.py
"""
Routing state and host-profile merge helpers for PlaywrightManager.
Used by composed manager class to apply temporary per-host strategy overrides.
Run: imported by browser facade during class composition.
Inputs: host keys, routing mappings, and strategy override payloads.
Outputs: resolved routing dictionaries and learning metadata snapshots.
Side effects: none directly; writes only occur via higher-level smart_fetch flow.
Operational notes: preserves legacy precedence and metadata semantics.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, Literal, Mapping, Optional, cast

from ..host_profiles import sanitize_routing_profile


class PlaywrightRoutingMixin:
    def _snapshot_routing_state(self) -> Dict[str, Any]:
        """Capture mutable routing attributes so per-host overrides can be temporary."""
        return {
            "serp_strategy": self.serp_strategy,
            "serp_retry_policy": self.serp_retry_policy,
            "serp_retry_backoff_seconds": self.serp_retry_backoff_seconds,
            "native_fallback_policy": self.native_fallback_policy,
            "native_browser_channels": tuple(self.native_browser_channels),
        }

    def _apply_routing_state(self, routing: Mapping[str, Any]) -> None:
        """Apply resolved routing controls for the current request run."""
        if "serp_strategy" in routing:
            value = str(routing["serp_strategy"]).strip().lower()
            if value in {"none", "native_first", "baseline_first"}:
                self.serp_strategy = cast(
                    Literal["none", "native_first", "baseline_first"],
                    value,
                )
        if "serp_retry_policy" in routing:
            value = str(routing["serp_retry_policy"]).strip().lower()
            if value in {"none", "balanced"}:
                self.serp_retry_policy = cast(Literal["none", "balanced"], value)
        if "serp_retry_backoff_seconds" in routing:
            try:
                self.serp_retry_backoff_seconds = max(
                    0.0,
                    float(routing["serp_retry_backoff_seconds"]),
                )
            except Exception:
                pass
        if "native_fallback_policy" in routing:
            value = str(routing["native_fallback_policy"]).strip().lower()
            if value in {"off", "on_blocked", "always"}:
                self.native_fallback_policy = cast(
                    Literal["off", "on_blocked", "always"],
                    value,
                )
        if "native_browser_channels" in routing:
            channels = sanitize_routing_profile(
                {"native_browser_channels": routing["native_browser_channels"]}
            ).get("native_browser_channels")
            if isinstance(channels, list) and channels:
                self.native_browser_channels = tuple(channels)

    def _restore_routing_state(self, state: Mapping[str, Any]) -> None:
        """Restore mutable routing attributes after a request completes."""
        self.serp_strategy = cast(
            Literal["none", "native_first", "baseline_first"],
            state.get("serp_strategy", self.serp_strategy),
        )
        self.serp_retry_policy = cast(
            Literal["none", "balanced"],
            state.get("serp_retry_policy", self.serp_retry_policy),
        )
        self.serp_retry_backoff_seconds = float(
            state.get(
                "serp_retry_backoff_seconds",
                self.serp_retry_backoff_seconds,
            )
        )
        self.native_fallback_policy = cast(
            Literal["off", "on_blocked", "always"],
            state.get("native_fallback_policy", self.native_fallback_policy),
        )
        channels = state.get("native_browser_channels", self.native_browser_channels)
        if isinstance(channels, tuple):
            self.native_browser_channels = channels
        elif isinstance(channels, list):
            self.native_browser_channels = tuple(channels)

    def _resolve_host_routing(
        self,
        *,
        host: str,
        strategy_overrides: Optional[Mapping[str, Any]] = None,
    ) -> tuple[Dict[str, Any], bool, Dict[str, str]]:
        """
        Resolve routing with precedence:
        explicit request overrides > host active profile > manager globals.
        """
        effective: Dict[str, Any] = {
            "serp_strategy": self.serp_strategy,
            "serp_retry_policy": self.serp_retry_policy,
            "serp_retry_backoff_seconds": self.serp_retry_backoff_seconds,
            "native_fallback_policy": self.native_fallback_policy,
            "native_browser_channels": list(self.native_browser_channels),
        }
        active_profile_applied = False

        if self.host_profiles_enabled and self._host_profile_store and host:
            host_routing, has_active_profile, match_metadata = (
                self._host_profile_store.resolve_strategy_with_match(host)
            )
            if has_active_profile and host_routing:
                effective.update(host_routing)
                active_profile_applied = True
            else:
                match_metadata = {"match_key": "", "match_scope": "none"}
        else:
            match_metadata = {"match_key": "", "match_scope": "none"}

        explicit_routing = sanitize_routing_profile(strategy_overrides or {})
        raw_explicit_policy = (
            str((strategy_overrides or {}).get("native_fallback_policy", "") or "")
            .strip()
            .lower()
        )
        if raw_explicit_policy in {"off", "on_blocked", "always"}:
            explicit_routing["native_fallback_policy"] = raw_explicit_policy
        if explicit_routing:
            effective.update(explicit_routing)
            active_profile_applied = False
            match_metadata = {"match_key": "", "match_scope": "explicit_override"}

        return effective, active_profile_applied, match_metadata

    def _build_learning_routing(self) -> Dict[str, Any]:
        safe_native_policy = (
            self.native_fallback_policy
            if self.native_fallback_policy in {"off", "on_blocked"}
            else "on_blocked"
        )
        return sanitize_routing_profile(
            {
                "serp_strategy": self.serp_strategy,
                "serp_retry_policy": self.serp_retry_policy,
                "serp_retry_backoff_seconds": self.serp_retry_backoff_seconds,
                "native_fallback_policy": safe_native_policy,
                "native_browser_channels": list(self.native_browser_channels),
            }
        )

    def _enrich_learning_metadata(self, *, host: str) -> Dict[str, Any]:
        metadata = dict(self._last_fetch_metadata)
        attempt_profile = str(metadata.get("attempt_profile", "") or "").lower()
        context_mode = "incognito"
        if attempt_profile.startswith("native_channel_"):
            context_mode = self.native_context_mode
        had_persisted_state = bool(context_mode == "persistent")
        promotion_eligible = bool(
            context_mode == "incognito" and not had_persisted_state
        )
        if host:
            metadata["host"] = host
        metadata["context_mode"] = context_mode
        metadata["had_persisted_state"] = had_persisted_state
        metadata["promotion_eligible"] = promotion_eligible
        if self._host_profile_store_error:
            metadata["host_profile_store_error"] = self._host_profile_store_error
        metadata["run_id"] = metadata.get("run_id") or datetime.datetime.now(
            datetime.timezone.utc
        ).strftime("run_%Y%m%dT%H%M%S%fZ")
        return metadata
