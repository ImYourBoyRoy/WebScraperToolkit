# ./src/web_scraper_toolkit/core/runtime.py
"""
Central runtime configuration and dynamic scaling helpers for CLI and MCP execution.
Used by `cli.py` and `server/mcp_server.py` to avoid hardcoded concurrency and timeout values.
Run: Imported as a library module; not a direct CLI entry point.
Inputs: `config.json`, optional local cfg files, environment variables, and explicit override dictionaries.
Outputs: Typed runtime settings, timeout profiles, and worker-count resolution utilities.
Side effects: Reads local configuration files and process environment.
Operational notes: Precedence is defaults < config.json < settings.local.cfg/settings.cfg < env < explicit overrides.
"""

from __future__ import annotations

import configparser
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    value_str = str(value).strip().lower()
    if value_str in {"1", "true", "yes", "on"}:
        return True
    if value_str in {"0", "false", "no", "off"}:
        return False
    return default


def _as_int(value: Any, default: int, min_value: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, parsed)


def _as_float(value: Any, default: float, min_value: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, parsed)


def _deep_update(target: MutableMapping[str, Any], updates: Mapping[str, Any]) -> None:
    for key, value in updates.items():
        if (
            key in target
            and isinstance(target[key], dict)
            and isinstance(value, Mapping)
        ):
            _deep_update(target[key], value)
            continue
        target[key] = value


def _load_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if isinstance(data, dict):
        return data
    return {}


def _load_local_cfg(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}

    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except OSError:
        return {}

    runtime: Dict[str, Any] = {}
    for section in parser.sections():
        values: Dict[str, Any] = {}
        for key, value in parser[section].items():
            values[key] = value

        if section.startswith("timeout."):
            profile_name = section.split(".", 1)[1].strip().lower()
            runtime.setdefault("timeouts", {})[profile_name] = values
            continue

        if section == "runtime":
            _deep_update(runtime, values)
            continue

        runtime[section] = values

    return {"runtime": runtime}


@dataclass(slots=True)
class TimeoutProfile:
    """Adaptive timeout profile for MCP and long-running scraping operations."""

    soft_seconds: int
    hard_seconds: int
    extension_seconds: int
    allow_extension: bool = True

    def normalized(self) -> "TimeoutProfile":
        soft = max(1, int(self.soft_seconds))
        hard = max(soft, int(self.hard_seconds))
        extension = max(0, int(self.extension_seconds))
        return TimeoutProfile(
            soft_seconds=soft,
            hard_seconds=hard,
            extension_seconds=extension,
            allow_extension=bool(self.allow_extension),
        )

    def scaled(self, work_units: int = 1) -> "TimeoutProfile":
        """
        Scale timeout budget by workload size.
        Keeps behavior stable for small tasks while allowing larger jobs to breathe.
        """
        normalized = self.normalized()
        units = max(1, int(work_units))
        multiplier = min(4.0, 1.0 + (units - 1) * 0.12)
        soft = int(normalized.soft_seconds * multiplier)
        hard = int(normalized.hard_seconds * multiplier)
        extension = int(normalized.extension_seconds * multiplier)
        return TimeoutProfile(
            soft_seconds=max(1, soft),
            hard_seconds=max(soft, hard),
            extension_seconds=max(0, extension),
            allow_extension=normalized.allow_extension,
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "soft_seconds": self.soft_seconds,
            "hard_seconds": self.hard_seconds,
            "extension_seconds": self.extension_seconds,
            "allow_extension": self.allow_extension,
        }


@dataclass(slots=True)
class ConcurrencySettings:
    """Concurrency controls for CLI scraping, MCP tools, and batch operations."""

    cli_workers_default: str = "auto"
    cli_workers_max: int = 32
    mcp_process_workers: int = 0
    mcp_inflight_limit: int = 0
    mcp_batch_workers: int = 0
    crawler_default_workers: int = 0
    crawler_max_workers: int = 128
    cpu_reserve: int = 1

    def as_dict(self) -> Dict[str, Any]:
        return {
            "cli_workers_default": self.cli_workers_default,
            "cli_workers_max": self.cli_workers_max,
            "mcp_process_workers": self.mcp_process_workers,
            "mcp_inflight_limit": self.mcp_inflight_limit,
            "mcp_batch_workers": self.mcp_batch_workers,
            "crawler_default_workers": self.crawler_default_workers,
            "crawler_max_workers": self.crawler_max_workers,
            "cpu_reserve": self.cpu_reserve,
        }


@dataclass(slots=True)
class ServerRuntimeSettings:
    """Server transport and security defaults for local and remote MCP hosting."""

    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000
    path: str = "/mcp"
    require_api_key: bool = False
    api_key_env: str = "WST_MCP_API_KEY"
    expose_server_banner: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return {
            "transport": self.transport,
            "host": self.host,
            "port": self.port,
            "path": self.path,
            "require_api_key": self.require_api_key,
            "api_key_env": self.api_key_env,
            "expose_server_banner": self.expose_server_banner,
        }


@dataclass(slots=True)
class RuntimeSettings:
    """Top-level runtime settings object shared across CLI and MCP server."""

    default_timeout_profile: str = "standard"
    concurrency: ConcurrencySettings = field(default_factory=ConcurrencySettings)
    server: ServerRuntimeSettings = field(default_factory=ServerRuntimeSettings)
    timeout_profiles: Dict[str, TimeoutProfile] = field(default_factory=dict)
    safe_output_root: str = "."
    job_retention_seconds: int = 3600
    max_job_records: int = 1000

    def get_timeout_profile(self, name: Optional[str] = None) -> TimeoutProfile:
        profile_name = (name or self.default_timeout_profile).strip().lower()
        selected = self.timeout_profiles.get(profile_name)
        if selected is None:
            selected = self.timeout_profiles["standard"]
        return selected.normalized()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "default_timeout_profile": self.default_timeout_profile,
            "safe_output_root": self.safe_output_root,
            "job_retention_seconds": self.job_retention_seconds,
            "max_job_records": self.max_job_records,
            "concurrency": self.concurrency.as_dict(),
            "server": self.server.as_dict(),
            "timeout_profiles": {
                name: profile.as_dict()
                for name, profile in self.timeout_profiles.items()
            },
        }


def _default_timeout_profiles() -> Dict[str, TimeoutProfile]:
    return {
        "fast": TimeoutProfile(soft_seconds=20, hard_seconds=45, extension_seconds=10),
        "standard": TimeoutProfile(
            soft_seconds=60,
            hard_seconds=180,
            extension_seconds=60,
        ),
        "research": TimeoutProfile(
            soft_seconds=180,
            hard_seconds=900,
            extension_seconds=300,
        ),
        "long": TimeoutProfile(
            soft_seconds=600,
            hard_seconds=3600,
            extension_seconds=900,
        ),
    }


def _default_runtime_dict() -> Dict[str, Any]:
    return {
        "runtime": {
            "default_timeout_profile": "standard",
            "safe_output_root": ".",
            "job_retention_seconds": 3600,
            "max_job_records": 1000,
            "concurrency": {
                "cli_workers_default": "auto",
                "cli_workers_max": 32,
                "mcp_process_workers": 0,
                "mcp_inflight_limit": 0,
                "mcp_batch_workers": 0,
                "crawler_default_workers": 0,
                "crawler_max_workers": 128,
                "cpu_reserve": 1,
            },
            "server": {
                "transport": "stdio",
                "host": "127.0.0.1",
                "port": 8000,
                "path": "/mcp",
                "require_api_key": False,
                "api_key_env": "WST_MCP_API_KEY",
                "expose_server_banner": True,
            },
            "timeouts": {
                name: profile.as_dict()
                for name, profile in _default_timeout_profiles().items()
            },
        }
    }


def _apply_env(runtime: Dict[str, Any]) -> None:
    """Apply environment-variable overrides with `WST_` prefix."""
    env_map = {
        "WST_TIMEOUT_PROFILE": ("runtime", "default_timeout_profile"),
        "WST_SAFE_OUTPUT_ROOT": ("runtime", "safe_output_root"),
        "WST_JOB_RETENTION_SECONDS": ("runtime", "job_retention_seconds"),
        "WST_MAX_JOB_RECORDS": ("runtime", "max_job_records"),
        "WST_CLI_WORKERS_DEFAULT": ("runtime", "concurrency", "cli_workers_default"),
        "WST_CLI_WORKERS_MAX": ("runtime", "concurrency", "cli_workers_max"),
        "WST_MCP_PROCESS_WORKERS": ("runtime", "concurrency", "mcp_process_workers"),
        "WST_MCP_INFLIGHT_LIMIT": ("runtime", "concurrency", "mcp_inflight_limit"),
        "WST_MCP_BATCH_WORKERS": ("runtime", "concurrency", "mcp_batch_workers"),
        "WST_CRAWLER_DEFAULT_WORKERS": (
            "runtime",
            "concurrency",
            "crawler_default_workers",
        ),
        "WST_CRAWLER_MAX_WORKERS": ("runtime", "concurrency", "crawler_max_workers"),
        "WST_CPU_RESERVE": ("runtime", "concurrency", "cpu_reserve"),
        "WST_SERVER_TRANSPORT": ("runtime", "server", "transport"),
        "WST_SERVER_HOST": ("runtime", "server", "host"),
        "WST_SERVER_PORT": ("runtime", "server", "port"),
        "WST_SERVER_PATH": ("runtime", "server", "path"),
        "WST_SERVER_REQUIRE_API_KEY": ("runtime", "server", "require_api_key"),
        "WST_SERVER_API_KEY_ENV": ("runtime", "server", "api_key_env"),
        "WST_SERVER_SHOW_BANNER": ("runtime", "server", "expose_server_banner"),
    }

    for env_name, key_path in env_map.items():
        if env_name not in os.environ:
            continue
        container: MutableMapping[str, Any] = runtime
        for key in key_path[:-1]:
            nested = container.get(key)
            if not isinstance(nested, dict):
                nested = {}
                container[key] = nested
            container = nested
        container[key_path[-1]] = os.environ[env_name]


def _to_runtime_settings(merged: Dict[str, Any]) -> RuntimeSettings:
    runtime = merged.get("runtime", {})
    if not isinstance(runtime, dict):
        runtime = {}

    timeout_profiles = _default_timeout_profiles()
    timeouts_cfg = runtime.get("timeouts", {})
    if isinstance(timeouts_cfg, dict):
        for name, raw_profile in timeouts_cfg.items():
            if not isinstance(raw_profile, dict):
                continue
            timeout_profiles[name.strip().lower()] = TimeoutProfile(
                soft_seconds=_as_int(
                    raw_profile.get("soft_seconds"),
                    timeout_profiles.get(
                        name, timeout_profiles["standard"]
                    ).soft_seconds,
                    min_value=1,
                ),
                hard_seconds=_as_int(
                    raw_profile.get("hard_seconds"),
                    timeout_profiles.get(
                        name, timeout_profiles["standard"]
                    ).hard_seconds,
                    min_value=1,
                ),
                extension_seconds=_as_int(
                    raw_profile.get("extension_seconds"),
                    timeout_profiles.get(
                        name, timeout_profiles["standard"]
                    ).extension_seconds,
                    min_value=0,
                ),
                allow_extension=_as_bool(
                    raw_profile.get("allow_extension"),
                    timeout_profiles.get(
                        name, timeout_profiles["standard"]
                    ).allow_extension,
                ),
            )

    concurrency_cfg = runtime.get("concurrency", {})
    if not isinstance(concurrency_cfg, dict):
        concurrency_cfg = {}

    server_cfg = runtime.get("server", {})
    if not isinstance(server_cfg, dict):
        server_cfg = {}

    settings = RuntimeSettings(
        default_timeout_profile=str(runtime.get("default_timeout_profile", "standard"))
        .strip()
        .lower(),
        concurrency=ConcurrencySettings(
            cli_workers_default=str(
                concurrency_cfg.get("cli_workers_default", "auto")
            ).strip(),
            cli_workers_max=_as_int(
                concurrency_cfg.get("cli_workers_max", 32),
                default=32,
                min_value=1,
            ),
            mcp_process_workers=_as_int(
                concurrency_cfg.get("mcp_process_workers", 0),
                default=0,
                min_value=0,
            ),
            mcp_inflight_limit=_as_int(
                concurrency_cfg.get("mcp_inflight_limit", 0),
                default=0,
                min_value=0,
            ),
            mcp_batch_workers=_as_int(
                concurrency_cfg.get("mcp_batch_workers", 0),
                default=0,
                min_value=0,
            ),
            crawler_default_workers=_as_int(
                concurrency_cfg.get("crawler_default_workers", 0),
                default=0,
                min_value=0,
            ),
            crawler_max_workers=_as_int(
                concurrency_cfg.get("crawler_max_workers", 128),
                default=128,
                min_value=1,
            ),
            cpu_reserve=_as_int(
                concurrency_cfg.get("cpu_reserve", 1),
                default=1,
                min_value=0,
            ),
        ),
        server=ServerRuntimeSettings(
            transport=str(server_cfg.get("transport", "stdio")).strip().lower(),
            host=str(server_cfg.get("host", "127.0.0.1")).strip(),
            port=_as_int(server_cfg.get("port", 8000), default=8000, min_value=1),
            path=str(server_cfg.get("path", "/mcp")).strip() or "/mcp",
            require_api_key=_as_bool(
                server_cfg.get("require_api_key", False), default=False
            ),
            api_key_env=str(server_cfg.get("api_key_env", "WST_MCP_API_KEY")).strip()
            or "WST_MCP_API_KEY",
            expose_server_banner=_as_bool(
                server_cfg.get("expose_server_banner", True), default=True
            ),
        ),
        timeout_profiles=timeout_profiles,
        safe_output_root=str(runtime.get("safe_output_root", ".")).strip() or ".",
        job_retention_seconds=_as_int(
            runtime.get("job_retention_seconds", 3600),
            default=3600,
            min_value=60,
        ),
        max_job_records=_as_int(
            runtime.get("max_job_records", 1000),
            default=1000,
            min_value=10,
        ),
    )

    if settings.default_timeout_profile not in settings.timeout_profiles:
        settings.default_timeout_profile = "standard"
    return settings


def load_runtime_settings(
    config_json_path: Optional[str] = None,
    local_cfg_path: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> RuntimeSettings:
    """
    Load runtime settings with strict precedence:
    defaults < config.json < settings.local.cfg/settings.cfg < env < explicit overrides.
    """
    merged = _default_runtime_dict()

    cfg_json = Path(
        config_json_path or os.environ.get("WST_CONFIG_JSON", "config.json")
    )
    if cfg_json.exists():
        cfg_data = _load_json_file(cfg_json)
        _deep_update(merged, cfg_data)

    cfg_candidates = []
    if local_cfg_path:
        cfg_candidates.append(Path(local_cfg_path))
    else:
        env_cfg = os.environ.get("WST_LOCAL_CFG")
        if env_cfg:
            cfg_candidates.append(Path(env_cfg))
        cfg_candidates.extend([Path("settings.local.cfg"), Path("settings.cfg")])

    for candidate in cfg_candidates:
        if candidate.exists():
            _deep_update(merged, _load_local_cfg(candidate))
            break

    _apply_env(merged)

    if overrides:
        _deep_update(merged, overrides)

    return _to_runtime_settings(merged)


def resolve_worker_count(
    requested: Optional[str | int],
    *,
    cpu_reserve: int = 1,
    max_workers: Optional[int] = None,
    fallback: int = 1,
) -> int:
    """
    Resolve a dynamic worker count from explicit or symbolic values.
    Supports: integer, "auto", "max", "dynamic", or None.
    """
    cpu_total = max(1, (os.cpu_count() or 1))
    dynamic_default = max(1, cpu_total - max(0, cpu_reserve))
    worker_count = fallback

    if requested is None:
        worker_count = fallback
    elif isinstance(requested, int):
        worker_count = requested
    else:
        request_text = requested.strip().lower()
        if request_text in {"auto", "max", "dynamic", "cpu"}:
            worker_count = dynamic_default
        else:
            worker_count = _as_int(request_text, fallback, min_value=1)

    if worker_count < 1:
        worker_count = 1

    if max_workers is not None and max_workers > 0:
        worker_count = min(worker_count, max_workers)

    return worker_count
