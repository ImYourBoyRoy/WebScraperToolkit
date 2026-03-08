# ./src/web_scraper_toolkit/core/_script_diagnostics/commands.py
"""
Build deterministic argv lists for script diagnostics execution routes.
Used by ScriptDiagnosticsRunner command methods in core.script_diagnostics.
Run: imported only; no direct CLI entrypoint.
Inputs: runner fields (python, scripts dir, output dir) and method options.
Outputs: command lists suitable for subprocess.run execution.
Side effects: none.
Operational notes: enforce same argument normalization as legacy implementation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence


def _extend_extra(command: list[str], extra_args: Optional[Sequence[str]]) -> None:
    if extra_args:
        command.extend([str(item) for item in extra_args])


def build_toolkit_route_command(
    *,
    python_executable: str,
    scripts_dir: Path,
    url: str,
    timeout_ms: int,
    skip_interactive: bool,
    include_headless_stage: bool,
    require_2xx_status: bool,
    save_artifacts: bool,
    artifacts_dir: Optional[str],
    fixture_record_path: Optional[str],
    fixture_replay_path: Optional[str],
    auto_commit_host_profile: bool,
    host_profiles_path: Optional[str],
    read_only: bool,
    log_level: str,
    extra_args: Optional[Sequence[str]],
) -> list[str]:
    command: list[str] = [
        python_executable,
        str(scripts_dir / "diag_toolkit_route.py"),
        "--url",
        url,
        "--timeout-ms",
        str(max(5_000, int(timeout_ms))),
        "--log-level",
        log_level,
    ]
    if skip_interactive:
        command.append("--skip-interactive")
    if include_headless_stage:
        command.append("--include-headless-stage")
    if require_2xx_status:
        command.append("--require-2xx")
    if save_artifacts:
        command.append("--save-artifacts")
    if artifacts_dir:
        command.extend(["--artifacts-dir", artifacts_dir])
    if fixture_record_path:
        command.extend(["--fixture-record", fixture_record_path])
    if fixture_replay_path:
        command.extend(["--fixture-replay", fixture_replay_path])
    if auto_commit_host_profile:
        command.append("--auto-commit-host-profile")
    if host_profiles_path:
        command.extend(["--host-profiles-path", host_profiles_path])
    if read_only:
        command.append("--read-only")
    _extend_extra(command, extra_args)
    return command


def build_challenge_matrix_command(
    *,
    python_executable: str,
    scripts_dir: Path,
    url: str,
    variants: str,
    runs_per_variant: int,
    browser: str,
    headless: bool,
    timeout_ms: int,
    hold_method: str,
    hold_seconds: float,
    skip_hold: bool,
    fixture_record_path: Optional[str],
    fixture_replay_path: Optional[str],
    extra_args: Optional[Sequence[str]],
) -> list[str]:
    command: list[str] = [
        python_executable,
        str(scripts_dir / "challenge_diagnostic_matrix.py"),
        "--url",
        url,
        "--variants",
        variants,
        "--runs-per-variant",
        str(max(1, int(runs_per_variant))),
        "--browser",
        browser,
        "--timeout-ms",
        str(max(10_000, int(timeout_ms))),
        "--hold-method",
        hold_method,
        "--hold-seconds",
        str(max(0.5, float(hold_seconds))),
    ]
    if headless:
        command.append("--headless")
    if skip_hold:
        command.append("--skip-hold")
    if fixture_record_path:
        command.extend(["--fixture-record", fixture_record_path])
    if fixture_replay_path:
        command.extend(["--fixture-replay", fixture_replay_path])
    _extend_extra(command, extra_args)
    return command


def build_bot_check_command(
    *,
    python_executable: str,
    scripts_dir: Path,
    out_dir: Path,
    test_url: str,
    browsers: str,
    modes: str,
    headless: bool,
    prefer_system: str,
    use_default_sites: bool,
    screenshots: bool,
    sites: str,
    extra_args: Optional[Sequence[str]],
) -> tuple[list[str], Path]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_json = out_dir / f"bot_check_{stamp}.json"
    command: list[str] = [
        python_executable,
        str(scripts_dir / "bot_check.py"),
        "--test-url",
        test_url,
        "--browsers",
        browsers,
        "--modes",
        modes,
        "--prefer-system",
        prefer_system,
        "--out-dir",
        str(out_dir),
        "--out-json",
        str(out_json),
    ]
    if headless:
        command.append("--headless")
    if use_default_sites:
        command.append("--use-default-sites")
    if screenshots:
        command.append("--screenshots")
    if sites.strip():
        command.extend(["--sites", sites])
    _extend_extra(command, extra_args)
    return command, out_json


def build_browser_info_command(
    *,
    python_executable: str,
    scripts_dir: Path,
    extra_args: Optional[Sequence[str]],
) -> list[str]:
    command: list[str] = [
        python_executable,
        str(scripts_dir / "get_browser_info.py"),
    ]
    _extend_extra(command, extra_args)
    return command
