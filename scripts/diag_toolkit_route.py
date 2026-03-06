# ./scripts/diag_toolkit_route.py
"""
Compatibility entrypoint for toolkit route diagnostics without site-specific naming.
Run: python ./scripts/diag_toolkit_route.py [args]
Inputs: all CLI arguments are forwarded to scripts/diag_toolkit_zoominfo.py.
Outputs: same outputs as the delegated diagnostic script (console + JSON report files).
Side effects: launches browser diagnostics through the delegated script path.
Operational notes: thin shim only; delegates directly to diag_toolkit_zoominfo.py.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    target_script = script_dir / "diag_toolkit_zoominfo.py"
    command = [sys.executable, str(target_script), *sys.argv[1:]]
    raise SystemExit(subprocess.call(command))


if __name__ == "__main__":
    main()
