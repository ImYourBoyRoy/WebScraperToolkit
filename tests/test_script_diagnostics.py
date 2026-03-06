# ./tests/test_script_diagnostics.py
"""
Validate script diagnostics wrappers that expose standalone scripts as toolkit APIs.
Run: pytest tests/test_script_diagnostics.py
Inputs: mocked subprocess outputs and temporary project roots.
Outputs: assertions on parsed report paths, JSON payload extraction, and argument handling.
Side effects: writes temporary JSON files under pytest tmp_path only.
Operational notes: no external browser/network calls; subprocess execution is fully mocked.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from web_scraper_toolkit.core import script_diagnostics


def test_split_cli_args_supports_quotes() -> None:
    parsed = script_diagnostics.split_cli_args('--flag "value with spaces" --x=1')
    assert parsed == ["--flag", "value with spaces", "--x=1"]


def test_runner_toolkit_route_loads_report_json(tmp_path: Path, monkeypatch) -> None:
    out_dir = tmp_path / "scripts" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "diag_toolkit_zoominfo_20260305_010101.json"
    report_payload = {"summary": {"progressed_stages": 1}}
    report_path.write_text(json.dumps(report_payload), encoding="utf-8")

    completed = SimpleNamespace(
        returncode=0,
        stdout=f"[*] JSON report saved: {report_path}\n",
        stderr="",
    )
    monkeypatch.setattr(script_diagnostics.subprocess, "run", lambda *a, **k: completed)

    runner = script_diagnostics.ScriptDiagnosticsRunner(
        project_root=tmp_path,
        python_executable="python",
    )
    result = runner.run_toolkit_route(url="https://example.com")

    assert result["success"] is True
    assert result["report_path"] == str(report_path.resolve())
    assert result["report_json"] == report_payload


def test_runner_browser_info_parses_stdout_json(tmp_path: Path, monkeypatch) -> None:
    payload = [{"browser_label": "chromium", "mode": {"name": "baseline"}}]
    completed = SimpleNamespace(
        returncode=0,
        stdout=json.dumps(payload),
        stderr="",
    )
    monkeypatch.setattr(script_diagnostics.subprocess, "run", lambda *a, **k: completed)

    runner = script_diagnostics.ScriptDiagnosticsRunner(
        project_root=tmp_path,
        python_executable="python",
    )
    result = runner.run_browser_info(save_to_file=True)

    assert result["success"] is True
    assert result["report_json"] == payload
    assert result["report_path"] is not None
    assert Path(result["report_path"]).is_file()


def test_toolkit_route_passes_autocommit_flags(tmp_path: Path, monkeypatch) -> None:
    out_dir = tmp_path / "scripts" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "diag_toolkit_zoominfo_20260305_020202.json"
    report_path.write_text("{}", encoding="utf-8")

    captured_command = {}

    def _fake_run(command, **kwargs):
        captured_command["argv"] = command
        return SimpleNamespace(
            returncode=0,
            stdout=f"[*] JSON report saved: {report_path}\n",
            stderr="",
        )

    monkeypatch.setattr(script_diagnostics.subprocess, "run", _fake_run)
    runner = script_diagnostics.ScriptDiagnosticsRunner(
        project_root=tmp_path,
        python_executable="python",
    )
    runner.run_toolkit_route(
        url="https://example.com",
        auto_commit_host_profile=True,
        host_profiles_path="./host_profiles.json",
        read_only=True,
    )
    argv = captured_command["argv"]
    assert argv[1].endswith("diag_toolkit_route.py")
    assert "--auto-commit-host-profile" in argv
    assert "--host-profiles-path" in argv
    assert "./host_profiles.json" in argv
    assert "--read-only" in argv


def test_toolkit_route_passes_strict_status_flag(tmp_path: Path, monkeypatch) -> None:
    out_dir = tmp_path / "scripts" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "diag_toolkit_zoominfo_20260305_030303.json"
    report_path.write_text("{}", encoding="utf-8")

    captured_command = {}

    def _fake_run(command, **kwargs):
        captured_command["argv"] = command
        return SimpleNamespace(
            returncode=0,
            stdout=f"[*] JSON report saved: {report_path}\n",
            stderr="",
        )

    monkeypatch.setattr(script_diagnostics.subprocess, "run", _fake_run)
    runner = script_diagnostics.ScriptDiagnosticsRunner(
        project_root=tmp_path,
        python_executable="python",
    )
    runner.run_toolkit_route(
        url="https://example.com",
        require_2xx_status=True,
    )
    argv = captured_command["argv"]
    assert "--require-2xx" in argv


def test_toolkit_route_passes_artifact_flags(tmp_path: Path, monkeypatch) -> None:
    out_dir = tmp_path / "scripts" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "diag_toolkit_zoominfo_20260305_040404.json"
    report_path.write_text("{}", encoding="utf-8")

    captured_command = {}

    def _fake_run(command, **kwargs):
        captured_command["argv"] = command
        return SimpleNamespace(
            returncode=0,
            stdout=f"[*] JSON report saved: {report_path}\n",
            stderr="",
        )

    monkeypatch.setattr(script_diagnostics.subprocess, "run", _fake_run)
    runner = script_diagnostics.ScriptDiagnosticsRunner(
        project_root=tmp_path,
        python_executable="python",
    )
    runner.run_toolkit_route(
        url="https://example.com",
        save_artifacts=True,
        artifacts_dir="./scripts/out/artifacts",
    )
    argv = captured_command["argv"]
    assert "--save-artifacts" in argv
    assert "--artifacts-dir" in argv
    assert "./scripts/out/artifacts" in argv
