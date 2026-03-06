# ./src/web_scraper_toolkit/core/_script_diagnostics/parsing.py
"""
Path and JSON parsing helpers for diagnostics script stdout/stderr outputs.
Used by ScriptDiagnosticsRunner to locate generated report artifacts.
Run: imported by diagnostics facade; not a direct executable module.
Inputs: stdout/stderr text, regex patterns, and diagnostics output directories.
Outputs: resolved Path instances and parsed JSON payload objects.
Side effects: none.
Operational notes: all helpers are deterministic and filesystem-safe.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional


def extract_path_from_output(
    *,
    stdout: str,
    stderr: str,
    pattern: str,
    project_root: Path,
) -> Optional[Path]:
    combined = "\n".join([stdout or "", stderr or ""])
    matches = re.findall(pattern, combined, flags=re.IGNORECASE | re.MULTILINE)
    if not matches:
        return None
    raw_path = matches[-1].strip().strip("'\"")
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = (project_root / raw_path).resolve()
    if candidate.exists():
        return candidate
    return None


def latest_file_with_prefix(*, out_dir: Path, prefix: str) -> Optional[Path]:
    candidates = sorted(
        out_dir.glob(f"{prefix}*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def latest_file_in_zoominfo_matrix_runs(*, out_dir: Path) -> Optional[Path]:
    matrix_root = out_dir / "zoominfo_diagnostic_matrix"
    candidates: list[Path] = []
    if matrix_root.exists():
        candidates.extend(
            matrix_root.glob("run_*/zoominfo_diagnostic_matrix_results.json")
        )
    candidates = sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def parse_stdout_json(stdout: str) -> Optional[Any]:
    content = stdout.strip()
    if not content:
        return None
    try:
        return json.loads(content)
    except Exception:
        return None
