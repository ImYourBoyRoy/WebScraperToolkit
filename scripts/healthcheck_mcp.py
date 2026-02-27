# ./scripts/healthcheck_mcp.py
"""
Check MCP server health over remote transport by calling the `health_check` MCP tool.
Used by start/status scripts for quick operational validation of MCP availability.
Run: `python scripts/healthcheck_mcp.py --url http://127.0.0.1:8000/mcp`.
Inputs: MCP URL and optional API key.
Outputs: JSON health summary to stdout and exit code 0 on healthy / 1 on unhealthy.
Side effects: Performs network calls to the configured MCP endpoint.
Operational notes: Uses FastMCP client transport; no file writes and no mutable server actions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any, Dict

from fastmcp import Client


def _parse_envelope(raw: str) -> Dict[str, Any]:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("MCP response envelope is not an object.")
    return parsed


async def check_health(url: str, api_key: str | None) -> Dict[str, Any]:
    client_kwargs: Dict[str, Any] = {"timeout": 30}
    if api_key:
        client_kwargs["auth"] = api_key

    async with Client(url, **client_kwargs) as client:
        result = await client.call_tool("health_check", {})
        if getattr(result, "is_error", False):
            raise RuntimeError(f"health_check returned error result: {result}")
        payload = getattr(result, "data", "")
        if not isinstance(payload, str) or not payload.strip():
            raise RuntimeError("health_check returned empty payload.")
        envelope = _parse_envelope(payload)
        return envelope


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MCP health check utility")
    parser.add_argument(
        "--url",
        type=str,
        default=os.environ.get("WST_REMOTE_MCP_URL", "http://127.0.0.1:8000/mcp"),
        help="Remote MCP URL.",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.environ.get("WST_REMOTE_MCP_API_KEY"),
        help="Optional API key for protected MCP endpoints.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        envelope = asyncio.run(check_health(args.url, args.api_key))
        healthy = envelope.get("status") == "success"
        print(json.dumps({"ok": healthy, "response": envelope}, indent=2))
        sys.exit(0 if healthy else 1)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
