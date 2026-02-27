# ./src/web_scraper_toolkit/server/path_safety.py
"""
Validate and normalize output file paths for MCP tools that write to disk.
Used by screenshot/PDF/download endpoints to prevent unsafe path traversal on remote hosts.
Run: Imported by MCP tool registration modules.
Inputs: User-provided path strings and configured safe output root.
Outputs: Absolute, validated filesystem paths under the allowed output root.
Side effects: Creates parent directories for validated output paths.
Operational notes: Raises ValueError when a path escapes the configured safe root.
"""

from __future__ import annotations

from pathlib import Path


def resolve_safe_output_path(path_value: str, safe_root: str) -> str:
    """Resolve a write path under the configured safe output root."""
    if not path_value.strip():
        raise ValueError("Output path cannot be empty.")

    root = Path(safe_root).expanduser().resolve()
    requested = Path(path_value).expanduser()
    if requested.is_absolute():
        candidate = requested.resolve()
    else:
        candidate = (root / requested).resolve()

    if candidate != root and root not in candidate.parents:
        raise ValueError(
            f"Output path must stay under safe root '{root}'. Received '{candidate}'."
        )

    candidate.parent.mkdir(parents=True, exist_ok=True)
    return str(candidate)
