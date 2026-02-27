# ./tests/test_runtime_config.py
"""
Validate runtime configuration precedence and adaptive worker resolution behavior.
Used to protect config hierarchy semantics for CLI and MCP runtime loading.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from web_scraper_toolkit.core.runtime import load_runtime_settings, resolve_worker_count


def test_runtime_config_precedence(tmp_path: Path) -> None:
    config_json = tmp_path / "config.json"
    local_cfg = tmp_path / "settings.local.cfg"

    config_json.write_text(
        json.dumps(
            {
                "runtime": {
                    "default_timeout_profile": "fast",
                    "concurrency": {
                        "mcp_process_workers": 3,
                        "cli_workers_default": "2",
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    local_cfg.write_text(
        "\n".join(
            [
                "[runtime]",
                "default_timeout_profile = research",
                "",
                "[concurrency]",
                "mcp_process_workers = 5",
            ]
        ),
        encoding="utf-8",
    )

    with patch.dict(
        "os.environ",
        {
            "WST_MCP_PROCESS_WORKERS": "7",
            "WST_TIMEOUT_PROFILE": "long",
        },
        clear=False,
    ):
        settings = load_runtime_settings(
            config_json_path=str(config_json),
            local_cfg_path=str(local_cfg),
        )

    assert settings.default_timeout_profile == "long"  # ENV overrides local+json
    assert settings.concurrency.mcp_process_workers == 7  # ENV wins
    assert settings.concurrency.cli_workers_default == "2"  # from config.json


def test_resolve_worker_count_dynamic() -> None:
    with patch("os.cpu_count", return_value=12):
        auto = resolve_worker_count("auto", cpu_reserve=2, max_workers=20, fallback=1)
        explicit = resolve_worker_count("9", cpu_reserve=1, max_workers=8, fallback=1)

    assert auto == 10
    assert explicit == 8
