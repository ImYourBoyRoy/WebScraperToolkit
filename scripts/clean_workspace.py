# ./scripts/clean_workspace.py
"""
Clean local runtime artifacts to keep the repository release-ready and deterministic.
Run: python ./scripts/clean_workspace.py [--project-root <path>] [--dry-run]
Inputs: project root path, optional dry-run flag, and built-in artifact target list.
Outputs: console summary of deleted (or planned) files/directories and counts.
Side effects: removes runtime/cache/log/output folders and files under the project root.
Operational notes: safe for repeated runs; only deletes known generated artifact targets.
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ARTIFACT_TARGETS: tuple[str, ...] = (
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".quality_gate_logs",
    "cache",
    "sessions",
    "test_output",
    "tests_output",
    "scripts/out",
    "scripts/*.log",
    "**/__pycache__",
)


@dataclass(slots=True)
class CleanStats:
    removed_files: int = 0
    removed_dirs: int = 0
    missing_targets: int = 0


def _iter_matches(root: Path, pattern: str) -> Iterable[Path]:
    if any(token in pattern for token in ("*", "?", "[")):
        return root.glob(pattern)
    target = root / pattern
    return [target]


def _remove_path(path: Path, dry_run: bool, stats: CleanStats) -> None:
    if not path.exists():
        stats.missing_targets += 1
        return
    if dry_run:
        print(f"[dry-run] would remove: {path}")
        if path.is_dir():
            stats.removed_dirs += 1
        else:
            stats.removed_files += 1
        return

    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        print(f"[removed-dir] {path}")
        stats.removed_dirs += 1
    else:
        path.unlink(missing_ok=True)
        print(f"[removed-file] {path}")
        stats.removed_files += 1


def run_cleanup(project_root: Path, dry_run: bool) -> CleanStats:
    stats = CleanStats()
    seen: set[Path] = set()
    for pattern in ARTIFACT_TARGETS:
        for match in _iter_matches(project_root, pattern):
            resolved = match.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            _remove_path(match, dry_run=dry_run, stats=stats)
    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Clean runtime artifacts from workspace."
    )
    parser.add_argument(
        "--project-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Project root path (defaults to parent of scripts directory).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned removals without deleting files.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    root = Path(args.project_root).resolve()
    stats = run_cleanup(root, dry_run=bool(args.dry_run))
    print(
        f"[summary] removed_dirs={stats.removed_dirs} "
        f"removed_files={stats.removed_files} "
        f"missing_targets={stats.missing_targets}"
    )


if __name__ == "__main__":
    main()
