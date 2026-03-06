# ./src/web_scraper_toolkit/_cli/bootstrap.py
"""
Config bootstrap helpers for CLI startup.
Used by cli facade to auto-seed missing local config/example files.
Run: imported by cli facade/runner only.
Inputs: config target paths and optional local override config path.
Outputs: dict payloads describing created files and bootstrap errors.
Side effects: may copy example config files into project root.
Operational notes: idempotent copy-if-missing behavior.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


def load_global_config(path: str = "config.json", logger=None):
    """Loads the global config.json if it exists."""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception as exc:
            if logger is not None:
                logger.warning(f"Failed to load config.json: {exc}")
    return {}


def bootstrap_default_config_files(
    *,
    config_path: str,
    local_config_path: str | None,
) -> dict:
    """
    Auto-bootstrap local config files when examples exist and targets are missing.

    Returns:
        {
            "created": [list of absolute file paths],
            "errors": [list of warning strings]
        }
    """
    created: list[str] = []
    errors: list[str] = []

    base_dir = Path.cwd()
    cfg_target = Path(config_path).expanduser()
    if not cfg_target.is_absolute():
        cfg_target = (base_dir / cfg_target).resolve()
    cfg_example = cfg_target.with_name("config.example.json")

    local_target: Path | None = None
    if local_config_path:
        local_target = Path(local_config_path).expanduser()
        if not local_target.is_absolute():
            local_target = (base_dir / local_target).resolve()
    else:
        local_target = (base_dir / "settings.local.cfg").resolve()
    local_example = local_target.with_name("settings.example.cfg")

    candidates: list[tuple[Path, Path]] = [
        (cfg_target, cfg_example),
        (base_dir / "host_profiles.json", base_dir / "host_profiles.example.json"),
        (local_target, local_example),
    ]

    for dst, src in candidates:
        try:
            did_create = _copy_if_missing(dst, src)
            if did_create:
                created.append(str(dst))
        except FileNotFoundError:
            continue
        except Exception as exc:
            errors.append(f"Bootstrap warning for {dst}: {exc}")

    return {"created": sorted(set(created)), "errors": errors}


def _copy_if_missing(dst: Path, src: Path) -> bool:
    if dst.exists():
        return False
    if not src.exists():
        raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return True
