# ./src/web_scraper_toolkit/core/_script_diagnostics/__init__.py
"""
Internal helpers for script diagnostics command construction and parsing.
Used by core.script_diagnostics facade to keep module API compatibility stable.
Run: imported by diagnostics facade only; no standalone command.
Inputs: runner options, script output streams, and project paths.
Outputs: command argv lists and parsed report path/JSON helpers.
Side effects: none.
Operational notes: this package is private and not part of public toolkit API.
"""

from .commands import (
    build_bot_check_command,
    build_browser_info_command,
    build_challenge_matrix_command,
    build_toolkit_route_command,
)
from .parsing import (
    extract_path_from_output,
    latest_file_in_zoominfo_matrix_runs,
    latest_file_with_prefix,
    parse_stdout_json,
)

__all__ = [
    "build_toolkit_route_command",
    "build_challenge_matrix_command",
    "build_bot_check_command",
    "build_browser_info_command",
    "extract_path_from_output",
    "latest_file_with_prefix",
    "latest_file_in_zoominfo_matrix_runs",
    "parse_stdout_json",
]
