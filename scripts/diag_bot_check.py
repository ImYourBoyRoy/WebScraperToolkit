# ./scripts/diag_bot_check.py
"""
Compatibility entrypoint for bot-surface diagnostics using canonical `diag_*.py` naming.
Run: python ./scripts/diag_bot_check.py [args]
Inputs: all CLI arguments are forwarded to scripts/bot_check.py.
Outputs: delegated script output (JSON reports, screenshots, and terminal logs).
Side effects: executes multi-browser diagnostics and writes artifacts to configured output paths.
Operational notes: naming shim only; preserves legacy bot_check.py behavior and flags.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    target_script = script_dir / "bot_check.py"
    command = [sys.executable, str(target_script), *sys.argv[1:]]
    raise SystemExit(subprocess.call(command))


if __name__ == "__main__":
    main()
