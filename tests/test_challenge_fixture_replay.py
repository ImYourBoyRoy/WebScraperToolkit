# ./tests/test_challenge_fixture_replay.py
"""
Validate sanitized fixture replay so challenge diagnostics stay deterministic without live target dependencies.
Run: `python -m pytest tests/test_challenge_fixture_replay.py -q`.
Inputs: committed JSON fixtures under ./tests/fixtures/challenge.
Outputs: assertions on replayed evidence and public script fixture modes.
Side effects: launches local Python subprocesses only for fixture replay script checks.
Operational notes: never performs live network calls.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from web_scraper_toolkit.diagnostics import replay_fixture

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "challenge"


def test_replay_cloudflare_blocked_fixture() -> None:
    payload = replay_fixture(FIXTURES_DIR / "cloudflare_blocked.json")
    evidence = payload["evidence"]
    assert evidence["likely_real_page"] is False
    assert evidence["challenge_detected"] is True
    assert evidence["content_quality"] in {"deny", "challenge"}


def test_replay_zoominfo_loop_fixture() -> None:
    payload = replay_fixture(FIXTURES_DIR / "zoominfo_px_then_cf_loop.json")
    evidence = payload["evidence"]
    assert evidence["likely_real_page"] is False
    assert evidence["challenge_detected"] is True
    assert evidence["deny_page_detected"] is True


def test_diag_toolkit_zoominfo_fixture_replay_exits_blocked() -> None:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "diag_toolkit_zoominfo.py"),
        "--fixture-replay",
        str(FIXTURES_DIR / "zoominfo_px_deny.json"),
    ]
    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 1
    assert "likely_real_page=False" in completed.stdout


def test_zoominfo_matrix_fixture_replay_is_not_false_positive() -> None:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "zoominfo_diagnostic_matrix.py"),
        "--fixture-replay",
        str(FIXTURES_DIR / "zoominfo_px_then_cf_loop.json"),
    ]
    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 1
    assert "likely_real=False" in completed.stdout
    assert "px_cookies_not_sent_on_revisit" not in completed.stdout
