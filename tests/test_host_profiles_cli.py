# ./tests/test_host_profiles_cli.py
"""
CLI and management tests for host profile operator tooling.
Run with `python -m pytest -q tests/test_host_profiles_cli.py`.
Inputs: temporary host profile stores and deterministic routing fixtures.
Outputs: assertions over inspect/diff/promote/demote/reset CLI and store flows.
Side effects: writes temporary JSON host profile stores under pytest temp directories.
Operational notes: keeps host mutations explicit and validates compact JSON output paths.
"""

from __future__ import annotations

import json
from pathlib import Path

from web_scraper_toolkit.browser.host_profiles import HostProfileStore
from web_scraper_toolkit.browser.host_profiles_cli import main


def test_manual_promote_demote_and_reset_flow(tmp_path: Path, capsys) -> None:
    store_path = tmp_path / "host_profiles.json"
    store = HostProfileStore(path=str(store_path), promotion_threshold=2)
    routing = {
        "headless": False,
        "stealth_mode": False,
        "native_fallback_policy": "always",
        "native_browser_channels": ["chrome"],
    }
    store.record_attempt(
        host="example.com",
        routing=routing,
        success=True,
        blocked_reason="none",
        context_mode="incognito",
        had_persisted_state=False,
        promotion_eligible=True,
        run_id="candidate_run",
        final_url="https://example.com",
        status=200,
        used_active_profile=False,
    )

    assert main(["--path", str(store_path), "promote", "example.com"]) == 0
    promoted_payload = capsys.readouterr().out
    assert "example.com" in promoted_payload

    inspection = store.inspect_host("example.com")
    assert inspection["has_active_profile"] is True

    assert main(["--path", str(store_path), "demote", "example.com"]) == 0
    capsys.readouterr()
    diff_payload = store.diff_host("example.com")
    assert diff_payload["candidate"]
    assert not diff_payload["active"]

    assert (
        main(["--path", str(store_path), "reset", "example.com", "--drop-audit"]) == 0
    )
    capsys.readouterr()
    reset_payload = store.inspect_host("example.com")
    assert reset_payload["active"] == {}
    assert reset_payload["candidate"] == {}


def test_cli_summary_and_diff_json(tmp_path: Path, capsys) -> None:
    store_path = tmp_path / "host_profiles.json"
    store = HostProfileStore(path=str(store_path), promotion_threshold=1)
    store.set_host_profile(
        "example.com",
        {
            "routing": {
                "headless": False,
                "stealth_mode": False,
                "native_fallback_policy": "always",
                "native_browser_channels": ["msedge"],
            }
        },
    )

    assert main(["--path", str(store_path), "--json", "summary"]) == 0
    summary_payload = json.loads(capsys.readouterr().out)
    assert summary_payload["host_count"] == 1
    assert summary_payload["hosts"][0]["host"] == "example.com"

    assert main(["--path", str(store_path), "--json", "diff", "example.com"]) == 0
    diff_payload = json.loads(capsys.readouterr().out)
    assert diff_payload["host"] == "example.com"
    assert "defaults_vs_active" in diff_payload["diff"]
