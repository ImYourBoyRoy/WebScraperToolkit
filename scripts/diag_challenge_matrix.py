# ./scripts/diag_challenge_matrix.py
"""
Compatibility entrypoint for challenge-matrix diagnostics using canonical `diag_*.py` naming.
Run: python ./scripts/diag_challenge_matrix.py [args]
Inputs: all CLI arguments are forwarded to scripts/challenge_diagnostic_matrix.py.
Outputs: same console logs, exit codes, and report artifacts as the delegated script.
Side effects: launches browser diagnostics and writes outputs under scripts/out when enabled.
Operational notes: thin shim for naming consistency; behavior is fully delegated to legacy script.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    target_script = script_dir / "challenge_diagnostic_matrix.py"
    command = [sys.executable, str(target_script), *sys.argv[1:]]
    raise SystemExit(subprocess.call(command))


if __name__ == "__main__":
    main()
