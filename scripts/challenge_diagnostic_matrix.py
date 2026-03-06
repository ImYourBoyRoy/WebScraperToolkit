# ./scripts/challenge_diagnostic_matrix.py
"""
Compatibility entrypoint for challenge matrix diagnostics with neutral naming.
Run: python ./scripts/challenge_diagnostic_matrix.py [args]
Inputs: all CLI arguments are forwarded to scripts/zoominfo_diagnostic_matrix.py.
Outputs: same matrix reports as the delegated diagnostic script.
Side effects: launches browser matrix diagnostics via the delegated implementation.
Operational notes: thin shim only; preserves existing behavior while exposing a generic command path.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    target_script = script_dir / "zoominfo_diagnostic_matrix.py"
    command = [sys.executable, str(target_script), *sys.argv[1:]]
    raise SystemExit(subprocess.call(command))


if __name__ == "__main__":
    main()
