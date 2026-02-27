# ./run_tests.py
"""
Run local unit tests for WebScraperToolkit with deterministic source imports.
Used by developers for quick validation outside CI workflows.
Run: `python run_tests.py` from project root.
Inputs: Test modules under `./tests` matching `test_*.py`.
Outputs: Console test summary and process exit code (0 pass, 1 fail).
Side effects: Scrubs `__pycache__` directories before execution for fresh imports.
Operational notes: Inserts `./src` in `sys.path` so editable installs are not required.
"""

from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path


def _clean_pycache(root_dir: Path) -> None:
    """Remove all __pycache__ folders under the project root."""
    for pycache_dir in root_dir.rglob("__pycache__"):
        shutil.rmtree(pycache_dir, ignore_errors=True)


def run_tests() -> None:
    """Discover and execute test modules under ./tests."""
    project_root = Path(__file__).resolve().parent
    _clean_pycache(project_root)

    src_path = project_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    loader = unittest.TestLoader()
    suite = loader.discover(str(project_root / "tests"), pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
