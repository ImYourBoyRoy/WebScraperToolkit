# ./src/web_scraper_toolkit/browser/_host_profiles/store.py
"""
JSON-backed host profile store with safe-subset learning and audit history.
Used by browser fetch pipelines and management/CLI profile administration.
Run: imported by `browser.host_profiles` facade; no direct command entrypoint.
Inputs: host identifiers, routing snapshots, and success/block telemetry.
Outputs: profile snapshots, resolved routing strategies, and updated host records.
Side effects: reads/writes local JSON store file using atomic replace writes.
Operational notes: promotion uses clean incognito evidence; read APIs are lock-protected.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Mapping, Optional

from ..domain_identity import host_lookup_candidates, normalize_host, registrable_domain
from .constants import (
    DEFAULT_DEMOTION_THRESHOLD,
    DEFAULT_FALLBACK_POLICY,
    DEFAULT_PROMOTION_THRESHOLD,
    DEFAULT_SESSION_POLICY,
    DEFAULT_WINDOW_DAYS,
    MAX_AUDIT_EVENTS,
    MAX_SAMPLE_RUNS,
)
from .sanitizers import _parse_iso, _utc_now_iso, sanitize_routing_profile


class HostProfileStore:
    """
    JSON-backed host profile store with safe-subset learning and audit history.
    """

    def __init__(
        self,
        *,
        path: str = "./host_profiles.json",
        promotion_threshold: int = DEFAULT_PROMOTION_THRESHOLD,
        demotion_threshold: int = DEFAULT_DEMOTION_THRESHOLD,
        window_days: int = DEFAULT_WINDOW_DAYS,
        apply_mode: str = "safe_subset",
        auto_create: bool = True,
    ) -> None:
        self.path = Path(path).expanduser()
        self.promotion_threshold = max(1, int(promotion_threshold))
        self.demotion_threshold = max(1, int(demotion_threshold))
        self.window_days = max(1, int(window_days))
        self.apply_mode = (
            "safe_subset"
            if str(apply_mode).strip().lower() != "safe_subset"
            else "safe_subset"
        )
        self._lock = RLock()
        self._cache: Optional[Dict[str, Any]] = None
        if auto_create:
            self.ensure_store_file()

    def _default_store(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "defaults": {
                "fallback_policy": DEFAULT_FALLBACK_POLICY,
                "session_policy": DEFAULT_SESSION_POLICY,
            },
            "hosts": {},
        }

    def _load_locked(self) -> Dict[str, Any]:
        if self._cache is not None:
            return self._cache

        if not self.path.exists():
            self._cache = self._default_store()
            return self._cache

        try:
            with self.path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except Exception:
            raw = self._default_store()

        if not isinstance(raw, dict):
            raw = self._default_store()
        raw.setdefault("version", 1)
        raw.setdefault(
            "defaults",
            {
                "fallback_policy": DEFAULT_FALLBACK_POLICY,
                "session_policy": DEFAULT_SESSION_POLICY,
            },
        )
        raw.setdefault("hosts", {})
        if not isinstance(raw["hosts"], dict):
            raw["hosts"] = {}
        self._cache = raw
        return self._cache

    def _save_locked(self) -> None:
        if self._cache is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(self._cache, handle, indent=2, sort_keys=True)
        tmp_path.replace(self.path)

    def ensure_store_file(self) -> None:
        """
        Ensure the profile store file exists with a valid base schema.

        Raises:
            OSError / PermissionError if the path cannot be created/written.
        """
        with self._lock:
            self._load_locked()
            self._save_locked()

    def _host_record_locked(self, host: str) -> Dict[str, Any]:
        store = self._load_locked()
        hosts = store.setdefault("hosts", {})
        record = hosts.get(host)
        if not isinstance(record, dict):
            record = {}
            hosts[host] = record
        return record

    def export_profiles(self, host: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            store = copy.deepcopy(self._load_locked())
        if host is None:
            return store
        host_key = normalize_host(host)
        return {
            "version": store.get("version", 1),
            "defaults": store.get("defaults", {}),
            "hosts": {
                host_key: copy.deepcopy(store.get("hosts", {}).get(host_key, {}))
            },
        }

    def resolve_strategy_with_match(
        self,
        host: str,
    ) -> tuple[Dict[str, Any], bool, Dict[str, str]]:
        """
        Resolve active routing strategy with exact-host then registrable-domain matching.

        Returns:
            (routing, has_active_profile, match_metadata)
        """
        host_key = normalize_host(host)
        if not host_key:
            return {}, False, {"match_key": "", "match_scope": "none"}
        with self._lock:
            store = self._load_locked()
            hosts = store.setdefault("hosts", {})
            for candidate_key, candidate_scope in host_lookup_candidates(host_key):
                record = hosts.get(candidate_key)
                if not isinstance(record, dict):
                    continue
                active = record.get("active")
                if not isinstance(active, dict):
                    continue
                routing = active.get("routing")
                if not isinstance(routing, dict):
                    continue
                return (
                    sanitize_routing_profile(routing),
                    True,
                    {
                        "match_key": candidate_key,
                        "match_scope": candidate_scope,
                    },
                )
        return {}, False, {"match_key": "", "match_scope": "none"}

    def resolve_strategy(self, host: str) -> tuple[Dict[str, Any], bool]:
        """
        Return the active host routing strategy and whether an active profile exists.
        """
        routing, has_profile, _ = self.resolve_strategy_with_match(host)
        return routing, has_profile

    def resolve_learning_target(self, host: str) -> tuple[str, str]:
        """
        Resolve which key should receive learning updates.

        Preference:
          1) exact host key if it already exists
          2) registrable domain key if it already exists
          3) registrable domain key (new record)
          4) exact host key fallback
        """
        exact_host = normalize_host(host)
        if not exact_host:
            return "", "none"
        domain_key = registrable_domain(exact_host)
        with self._lock:
            store = self._load_locked()
            hosts = store.setdefault("hosts", {})
            if isinstance(hosts.get(exact_host), dict):
                return exact_host, "exact"
            if domain_key and isinstance(hosts.get(domain_key), dict):
                return domain_key, "domain"
        if domain_key:
            return domain_key, "domain"
        return exact_host, "exact"

    def clear_host_profile(self, host: str) -> bool:
        host_key = normalize_host(host)
        if not host_key:
            return False
        with self._lock:
            store = self._load_locked()
            hosts = store.setdefault("hosts", {})
            if host_key in hosts:
                del hosts[host_key]
                self._save_locked()
                return True
        return False

    def set_host_profile(
        self, host: str, profile_payload: Mapping[str, Any]
    ) -> Dict[str, Any]:
        host_key = normalize_host(host)
        if not host_key:
            raise ValueError("host is required")
        payload = dict(profile_payload)
        routing_input = payload.get("routing", payload)
        if not isinstance(routing_input, dict):
            raise ValueError("profile payload must include a routing object")
        routing = sanitize_routing_profile(routing_input)
        if not routing:
            raise ValueError(
                "profile payload did not include valid safe routing fields"
            )
        now = _utc_now_iso()
        active = {
            "routing": routing,
            "learned_from": {
                "success_count": self.promotion_threshold,
                "window_days": self.window_days,
                "source": "manual",
            },
            "updated_utc": now,
            "health": {
                "clean_incognito_failures": 0,
                "window_days": self.window_days,
                "failure_timestamps": [],
            },
        }
        with self._lock:
            record = self._host_record_locked(host_key)
            record["active"] = active
            record.pop("candidate", None)
            self._save_locked()
        return copy.deepcopy(active)

    def _append_audit_event(
        self,
        *,
        record: Dict[str, Any],
        event: Dict[str, Any],
    ) -> None:
        audit = record.get("audit")
        if not isinstance(audit, list):
            audit = []
            record["audit"] = audit
        audit.append(event)
        if len(audit) > MAX_AUDIT_EVENTS:
            record["audit"] = audit[-MAX_AUDIT_EVENTS:]

    def _active_health_locked(self, active: Dict[str, Any]) -> Dict[str, Any]:
        health = active.get("health")
        if not isinstance(health, dict):
            health = {}
            active["health"] = health
        health.setdefault("clean_incognito_failures", 0)
        health.setdefault("window_days", self.window_days)
        timestamps = health.get("failure_timestamps")
        if not isinstance(timestamps, list):
            timestamps = []
            health["failure_timestamps"] = timestamps
        return health

    def _prune_failure_timestamps(
        self, timestamps: list[str], now_iso: str
    ) -> list[str]:
        now_dt = _parse_iso(now_iso) or datetime.now(timezone.utc)
        cutoff = now_dt - timedelta(days=self.window_days)
        kept: list[str] = []
        for raw in timestamps:
            dt = _parse_iso(str(raw))
            if dt and dt >= cutoff:
                kept.append(dt.isoformat())
        return kept

    def _candidate_template(
        self, routing: Dict[str, Any], now_iso: str
    ) -> Dict[str, Any]:
        return {
            "routing": routing,
            "evidence": {
                "clean_incognito_successes": 0,
                "clean_incognito_failures": 0,
                "persistent_successes": 0,
                "persistent_failures": 0,
                "last_seen_utc": now_iso,
                "sample_runs": [],
            },
        }

    def record_attempt(
        self,
        *,
        host: str,
        scope: str = "exact",
        routing: Mapping[str, Any],
        success: bool,
        blocked_reason: str,
        context_mode: str,
        had_persisted_state: bool,
        promotion_eligible: bool,
        run_id: str,
        final_url: str,
        status: Optional[int],
        used_active_profile: bool,
    ) -> Dict[str, Any]:
        """
        Record one fetch run and update candidate/active host profile state.
        """
        host_key = normalize_host(host)
        if not host_key:
            return {}
        routing_clean = sanitize_routing_profile(routing)
        now = _utc_now_iso()

        with self._lock:
            record = self._host_record_locked(host_key)
            active = record.get("active")
            active_routing = (
                sanitize_routing_profile(active.get("routing", {}))
                if isinstance(active, dict)
                else {}
            )

            self._append_audit_event(
                record=record,
                event={
                    "run_id": run_id,
                    "seen_utc": now,
                    "success": bool(success),
                    "blocked_reason": blocked_reason,
                    "context_mode": str(context_mode),
                    "had_persisted_state": bool(had_persisted_state),
                    "promotion_eligible": bool(promotion_eligible),
                    "used_active_profile": bool(used_active_profile),
                    "status": status,
                    "final_url": final_url,
                    "scope": scope,
                    "routing": routing_clean,
                },
            )

            if (
                isinstance(active, dict)
                and used_active_profile
                and routing_clean == active_routing
            ):
                health = self._active_health_locked(active)
                timestamps = [
                    str(ts)
                    for ts in health.get("failure_timestamps", [])
                    if isinstance(ts, str)
                ]
                timestamps = self._prune_failure_timestamps(timestamps, now)

                if promotion_eligible and success:
                    timestamps = []
                    health["clean_incognito_failures"] = 0
                elif promotion_eligible and not success:
                    timestamps.append(now)
                    timestamps = self._prune_failure_timestamps(timestamps, now)
                    health["clean_incognito_failures"] = len(timestamps)
                else:
                    health["clean_incognito_failures"] = len(timestamps)

                health["failure_timestamps"] = timestamps
                active["updated_utc"] = now

                if (
                    bool(health["clean_incognito_failures"])
                    and int(health["clean_incognito_failures"])
                    >= self.demotion_threshold
                ):
                    record["candidate"] = {
                        "routing": active_routing,
                        "evidence": {
                            "clean_incognito_successes": 0,
                            "clean_incognito_failures": int(
                                health["clean_incognito_failures"]
                            ),
                            "persistent_successes": 0,
                            "persistent_failures": 0,
                            "last_seen_utc": now,
                            "sample_runs": [run_id] if run_id else [],
                        },
                    }
                    record.pop("active", None)
            else:
                if not routing_clean:
                    self._save_locked()
                    return copy.deepcopy(record)

                candidate = record.get("candidate")
                if not isinstance(candidate, dict):
                    candidate = self._candidate_template(routing_clean, now)
                    record["candidate"] = candidate
                if (
                    sanitize_routing_profile(candidate.get("routing", {}))
                    != routing_clean
                ):
                    candidate = self._candidate_template(routing_clean, now)
                    record["candidate"] = candidate

                evidence = candidate.get("evidence")
                if not isinstance(evidence, dict):
                    evidence = self._candidate_template(routing_clean, now)["evidence"]
                    candidate["evidence"] = evidence
                candidate["routing"] = routing_clean
                evidence.setdefault("clean_incognito_successes", 0)
                evidence.setdefault("clean_incognito_failures", 0)
                evidence.setdefault("persistent_successes", 0)
                evidence.setdefault("persistent_failures", 0)
                evidence.setdefault("sample_runs", [])

                if promotion_eligible:
                    if success:
                        evidence["clean_incognito_successes"] = (
                            int(evidence["clean_incognito_successes"]) + 1
                        )
                    else:
                        evidence["clean_incognito_failures"] = (
                            int(evidence["clean_incognito_failures"]) + 1
                        )
                else:
                    if success:
                        evidence["persistent_successes"] = (
                            int(evidence["persistent_successes"]) + 1
                        )
                    else:
                        evidence["persistent_failures"] = (
                            int(evidence["persistent_failures"]) + 1
                        )

                sample_runs = [
                    str(item) for item in evidence.get("sample_runs", []) if str(item)
                ]
                if run_id:
                    sample_runs.append(run_id)
                evidence["sample_runs"] = sample_runs[-MAX_SAMPLE_RUNS:]
                evidence["last_seen_utc"] = now

                if (
                    int(evidence["clean_incognito_successes"])
                    >= self.promotion_threshold
                ):
                    record["active"] = {
                        "routing": routing_clean,
                        "learned_from": {
                            "success_count": int(evidence["clean_incognito_successes"]),
                            "window_days": self.window_days,
                        },
                        "updated_utc": now,
                        "health": {
                            "clean_incognito_failures": 0,
                            "window_days": self.window_days,
                            "failure_timestamps": [],
                        },
                    }
                    record.pop("candidate", None)

            self._save_locked()
            return copy.deepcopy(record)
