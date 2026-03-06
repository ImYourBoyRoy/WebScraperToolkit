# ./scripts/diag_browser_info.py
"""
Compatibility entrypoint for browser telemetry diagnostics using canonical `diag_*.py` naming.
Run: python ./scripts/diag_browser_info.py [args]
Inputs: all CLI arguments are forwarded to scripts/get_browser_info.py.
Outputs: same JSON/text telemetry artifacts as the delegated browser-info script.
Side effects: launches browser fingerprint probes and writes results to output directory.
Operational notes: lightweight forwarding wrapper; keeps legacy entrypoint compatibility.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    target_script = script_dir / "get_browser_info.py"
    command = [sys.executable, str(target_script), *sys.argv[1:]]
    raise SystemExit(subprocess.call(command))


if __name__ == "__main__":
    main()
