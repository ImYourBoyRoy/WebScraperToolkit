# ./src/web_scraper_toolkit/core/script_diagnostics.py
"""
Expose standalone diagnostics scripts as callable toolkit primitives.
Used by CLI and MCP handlers to execute script-based diagnostics with structured outputs.
Run: import helper functions or use ScriptDiagnosticsRunner methods from toolkit code.
Inputs: target URLs, tool mode selections, optional passthrough CLI args, and per-tool toggles.
Outputs: normalized execution payloads with stdout/stderr, exit codes, report paths, and parsed JSON.
Side effects: launches local Python subprocesses and browser sessions driven by scripts in ./scripts.
Operational notes: testing-focused only; defaults favor deterministic report capture and safe argument parsing.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ._script_diagnostics.commands import (
    build_bot_check_command,
    build_browser_info_command,
    build_challenge_matrix_command,
    build_toolkit_route_command,
)
from ._script_diagnostics.parsing import (
    extract_path_from_output,
    latest_file_in_zoominfo_matrix_runs,
    latest_file_with_prefix,
    parse_stdout_json,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@lru_cache(maxsize=512)
def _split_cli_args_cached(raw: str) -> tuple[str, ...]:
    """Cached argv splitter for hot-path diagnostic argument parsing."""
    if not raw.strip():
        return ()
    tokens = shlex.split(raw, posix=False)
    normalized: List[str] = []
    for token in tokens:
        if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}:
            normalized.append(token[1:-1])
        else:
            normalized.append(token)
    return tuple(normalized)


def split_cli_args(raw: str) -> List[str]:
    """Split a shell-like argument string into argv tokens."""
    return list(_split_cli_args_cached(raw))


def _safe_read_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


@dataclass
class ScriptDiagnosticRun:
    tool: str
    command: List[str]
    cwd: str
    started_utc: str
    ended_utc: str
    elapsed_ms: int
    return_code: int
    success: bool
    stdout: str
    stderr: str
    report_path: Optional[str]
    report_json: Optional[Any]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ScriptDiagnosticsRunner:
    """Run toolkit script diagnostics and return normalized result payloads."""

    def __init__(
        self,
        *,
        project_root: Optional[Path] = None,
        python_executable: Optional[str] = None,
    ) -> None:
        if project_root is None:
            project_root = Path(__file__).resolve().parents[3]
        self.project_root = project_root
        self.scripts_dir = self.project_root / "scripts"
        self.out_dir = self.scripts_dir / "out"
        self.python_executable = python_executable or sys.executable

    def run_toolkit_route(
        self,
        *,
        url: str,
        timeout_ms: int = 45_000,
        skip_interactive: bool = False,
        include_headless_stage: bool = False,
        require_2xx_status: bool = False,
        save_artifacts: bool = False,
        artifacts_dir: Optional[str] = None,
        fixture_record_path: Optional[str] = None,
        fixture_replay_path: Optional[str] = None,
        auto_commit_host_profile: bool = False,
        host_profiles_path: Optional[str] = None,
        read_only: bool = False,
        log_level: str = "INFO",
        extra_args: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        command = build_toolkit_route_command(
            python_executable=self.python_executable,
            scripts_dir=self.scripts_dir,
            url=url,
            timeout_ms=timeout_ms,
            skip_interactive=skip_interactive,
            include_headless_stage=include_headless_stage,
            require_2xx_status=require_2xx_status,
            save_artifacts=save_artifacts,
            artifacts_dir=artifacts_dir,
            fixture_record_path=fixture_record_path,
            fixture_replay_path=fixture_replay_path,
            auto_commit_host_profile=auto_commit_host_profile,
            host_profiles_path=host_profiles_path,
            read_only=read_only,
            log_level=log_level,
            extra_args=extra_args,
        )
        run = self._run_subprocess(command)
        report_path = extract_path_from_output(
            stdout=run.stdout,
            stderr=run.stderr,
            pattern=r"JSON report saved:\s*(.+)$",
            project_root=self.project_root,
        )
        if report_path is None:
            report_path = latest_file_with_prefix(
                out_dir=self.out_dir,
                prefix="diag_toolkit_zoominfo_",
            )
        return self._finalize(run, report_path)

    def run_challenge_matrix(
        self,
        *,
        url: str,
        variants: str = "baseline,minimal_stealth,legacy_stealth",
        runs_per_variant: int = 1,
        browser: str = "chrome",
        headless: bool = False,
        timeout_ms: int = 90_000,
        hold_method: str = "auto",
        hold_seconds: float = 12.0,
        skip_hold: bool = False,
        fixture_record_path: Optional[str] = None,
        fixture_replay_path: Optional[str] = None,
        extra_args: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        command = build_challenge_matrix_command(
            python_executable=self.python_executable,
            scripts_dir=self.scripts_dir,
            url=url,
            variants=variants,
            runs_per_variant=runs_per_variant,
            browser=browser,
            headless=headless,
            timeout_ms=timeout_ms,
            hold_method=hold_method,
            hold_seconds=hold_seconds,
            skip_hold=skip_hold,
            fixture_record_path=fixture_record_path,
            fixture_replay_path=fixture_replay_path,
            extra_args=extra_args,
        )
        run = self._run_subprocess(command)
        report_path = extract_path_from_output(
            stdout=run.stdout,
            stderr=run.stderr,
            pattern=r"JSON:\s*(.+zoominfo_diagnostic_matrix_results\.json)$",
            project_root=self.project_root,
        )
        if report_path is None:
            report_path = latest_file_in_zoominfo_matrix_runs(out_dir=self.out_dir)
        return self._finalize(run, report_path)

    def run_bot_check(
        self,
        *,
        test_url: str = "https://example.com/",
        browsers: str = "chromium,pw_chrome,system_chrome",
        modes: str = "baseline,stealth",
        headless: bool = False,
        prefer_system: str = "chrome",
        use_default_sites: bool = False,
        screenshots: bool = False,
        sites: str = "",
        extra_args: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        command, out_json = build_bot_check_command(
            python_executable=self.python_executable,
            scripts_dir=self.scripts_dir,
            out_dir=self.out_dir,
            test_url=test_url,
            browsers=browsers,
            modes=modes,
            headless=headless,
            prefer_system=prefer_system,
            use_default_sites=use_default_sites,
            screenshots=screenshots,
            sites=sites,
            extra_args=extra_args,
        )
        run = self._run_subprocess(command)
        return self._finalize(run, out_json if out_json.exists() else None)

    def run_browser_info(
        self,
        *,
        save_to_file: bool = True,
        extra_args: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        command = build_browser_info_command(
            python_executable=self.python_executable,
            scripts_dir=self.scripts_dir,
            extra_args=extra_args,
        )
        run = self._run_subprocess(command)

        parsed_stdout = parse_stdout_json(run.stdout)
        report_path: Optional[Path] = None
        if save_to_file and parsed_stdout is not None:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            report_path = self.out_dir / f"get_browser_info_{stamp}.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(parsed_stdout, indent=2), encoding="utf-8"
            )
        finalized = self._finalize(run, report_path)
        if parsed_stdout is not None and finalized["report_json"] is None:
            finalized["report_json"] = parsed_stdout
        return finalized

    def _run_subprocess(self, command: List[str]) -> ScriptDiagnosticRun:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        started_utc = _utc_now_iso()
        start = time.perf_counter()
        completed = subprocess.run(
            command,
            cwd=str(self.project_root),
            text=True,
            capture_output=True,
            check=False,
        )
        ended_utc = _utc_now_iso()
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return ScriptDiagnosticRun(
            tool=Path(command[1]).stem if len(command) > 1 else "unknown",
            command=command,
            cwd=str(self.project_root),
            started_utc=started_utc,
            ended_utc=ended_utc,
            elapsed_ms=elapsed_ms,
            return_code=completed.returncode,
            success=completed.returncode == 0,
            stdout=completed.stdout,
            stderr=completed.stderr,
            report_path=None,
            report_json=None,
        )

    def _finalize(
        self,
        run: ScriptDiagnosticRun,
        report_path: Optional[Path],
    ) -> Dict[str, Any]:
        json_payload = None
        normalized_path: Optional[str] = None
        if report_path is not None:
            normalized_path = str(report_path.resolve())
            json_payload = _safe_read_json(report_path)
        run.report_path = normalized_path
        run.report_json = json_payload
        return run.as_dict()


def run_toolkit_route_diagnostic(
    *,
    url: str,
    timeout_ms: int = 45_000,
    skip_interactive: bool = False,
    include_headless_stage: bool = False,
    require_2xx_status: bool = False,
    save_artifacts: bool = False,
    artifacts_dir: Optional[str] = None,
    fixture_record_path: Optional[str] = None,
    fixture_replay_path: Optional[str] = None,
    auto_commit_host_profile: bool = False,
    host_profiles_path: Optional[str] = None,
    read_only: bool = False,
    log_level: str = "INFO",
    extra_args: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    runner = ScriptDiagnosticsRunner()
    return runner.run_toolkit_route(
        url=url,
        timeout_ms=timeout_ms,
        skip_interactive=skip_interactive,
        include_headless_stage=include_headless_stage,
        require_2xx_status=require_2xx_status,
        save_artifacts=save_artifacts,
        artifacts_dir=artifacts_dir,
        fixture_record_path=fixture_record_path,
        fixture_replay_path=fixture_replay_path,
        auto_commit_host_profile=auto_commit_host_profile,
        host_profiles_path=host_profiles_path,
        read_only=read_only,
        log_level=log_level,
        extra_args=extra_args,
    )


def run_challenge_matrix_diagnostic(
    *,
    url: str,
    variants: str = "baseline,minimal_stealth,legacy_stealth",
    runs_per_variant: int = 1,
    browser: str = "chrome",
    headless: bool = False,
    timeout_ms: int = 90_000,
    hold_method: str = "auto",
    hold_seconds: float = 12.0,
    skip_hold: bool = False,
    fixture_record_path: Optional[str] = None,
    fixture_replay_path: Optional[str] = None,
    extra_args: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    runner = ScriptDiagnosticsRunner()
    return runner.run_challenge_matrix(
        url=url,
        variants=variants,
        runs_per_variant=runs_per_variant,
        browser=browser,
        headless=headless,
        timeout_ms=timeout_ms,
        hold_method=hold_method,
        hold_seconds=hold_seconds,
        skip_hold=skip_hold,
        fixture_record_path=fixture_record_path,
        fixture_replay_path=fixture_replay_path,
        extra_args=extra_args,
    )


def run_bot_check_diagnostic(
    *,
    test_url: str = "https://example.com/",
    browsers: str = "chromium,pw_chrome,system_chrome",
    modes: str = "baseline,stealth",
    headless: bool = False,
    prefer_system: str = "chrome",
    use_default_sites: bool = False,
    screenshots: bool = False,
    sites: str = "",
    extra_args: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    runner = ScriptDiagnosticsRunner()
    return runner.run_bot_check(
        test_url=test_url,
        browsers=browsers,
        modes=modes,
        headless=headless,
        prefer_system=prefer_system,
        use_default_sites=use_default_sites,
        screenshots=screenshots,
        sites=sites,
        extra_args=extra_args,
    )


def run_browser_info_diagnostic(
    *,
    save_to_file: bool = True,
    extra_args: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    runner = ScriptDiagnosticsRunner()
    return runner.run_browser_info(save_to_file=save_to_file, extra_args=extra_args)
