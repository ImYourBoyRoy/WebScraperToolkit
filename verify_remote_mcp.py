# ./verify_remote_mcp.py
"""
Run remote MCP smoke checks against a deployed Web Scraper Toolkit instance.
Used by operators to validate remote transport, auth, tool availability, and job lifecycle behavior.
Run: `python verify_remote_mcp.py --remote-url https://host.example.com/mcp`.
Inputs: Remote MCP URL, optional API key, target URLs, and poll timeout arguments.
Outputs: Exit code 0 on pass, 1 on fail, with JSON summary printed to stdout.
Side effects: Executes read-oriented MCP tool calls against the remote instance.
Operational notes: Intended for pre-release and post-deploy health checks; avoids file-writing tools by default.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any, Dict, List

from fastmcp import Client


def _parse_envelope(raw: str) -> Dict[str, Any]:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("MCP response envelope is not an object.")
    return parsed


async def _call_tool(
    client: Client, name: str, arguments: Dict[str, Any]
) -> Dict[str, Any]:
    result = await client.call_tool(name, arguments)
    if getattr(result, "is_error", False):
        raise RuntimeError(f"Tool {name} returned an error result: {result}")
    raw = getattr(result, "data", "")
    if not isinstance(raw, str) or not raw.strip():
        raise RuntimeError(f"Tool {name} returned empty payload.")
    envelope = _parse_envelope(raw)
    return envelope


async def run_smoke_checks(
    remote_url: str,
    api_key: str | None,
    targets: List[str],
    poll_timeout_seconds: int,
) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"remote_url": remote_url, "checks": []}
    client_kwargs: Dict[str, Any] = {"timeout": 120}
    if api_key:
        client_kwargs["auth"] = api_key

    async with Client(remote_url, **client_kwargs) as client:
        tools = await client.list_tools()
        tool_names = {tool.name for tool in tools}
        required = {
            "health_check",
            "scrape_url",
            "start_job",
            "poll_job",
            "cancel_job",
            "list_jobs",
        }
        missing = sorted(required - tool_names)
        summary["checks"].append(
            {
                "name": "tool_registry",
                "ok": not missing,
                "details": {"tool_count": len(tool_names), "missing": missing},
            }
        )
        if missing:
            raise RuntimeError(f"Missing required remote tools: {missing}")

        health = await _call_tool(client, "health_check", {})
        summary["checks"].append(
            {
                "name": "health_check",
                "ok": health.get("status") == "success",
                "details": health.get("data", {}),
            }
        )

        scrape_target = targets[0]
        scrape = await _call_tool(
            client,
            "scrape_url",
            {
                "url": scrape_target,
                "format": "markdown",
                "max_length": 2000,
                "timeout_profile": "standard",
            },
        )
        scrape_data = scrape.get("data", "")
        scrape_ok = (
            scrape.get("status") == "success"
            and isinstance(scrape_data, str)
            and len(scrape_data) > 0
        )
        summary["checks"].append(
            {
                "name": "scrape_url",
                "ok": scrape_ok,
                "details": {
                    "target": scrape_target,
                    "length": len(scrape_data) if isinstance(scrape_data, str) else 0,
                },
            }
        )
        if not scrape_ok:
            raise RuntimeError("scrape_url smoke check failed.")

        payload = json.dumps({"urls": targets, "format": "markdown"})
        start_job = await _call_tool(
            client,
            "start_job",
            {
                "job_type": "batch_scrape",
                "payload_json": payload,
                "timeout_profile": "research",
            },
        )
        job_data = start_job.get("data", {})
        if not isinstance(job_data, dict) or "job_id" not in job_data:
            raise RuntimeError(f"start_job did not return job_id: {start_job}")
        job_id = str(job_data["job_id"])

        deadline = time.time() + max(15, poll_timeout_seconds)
        terminal_state = "running"
        while time.time() < deadline:
            poll = await _call_tool(
                client,
                "poll_job",
                {"job_id": job_id, "include_result": True},
            )
            poll_data = poll.get("data", {})
            terminal_state = str(poll_data.get("status", "unknown"))
            if terminal_state in {"completed", "failed", "timeout", "cancelled"}:
                break
            await asyncio.sleep(1.0)

        summary["checks"].append(
            {
                "name": "async_job_lifecycle",
                "ok": terminal_state in {"completed", "failed", "timeout", "cancelled"},
                "details": {"job_id": job_id, "final_status": terminal_state},
            }
        )

    summary["ok"] = all(check["ok"] for check in summary["checks"])
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify remote MCP deployment health.")
    parser.add_argument(
        "--remote-url",
        type=str,
        default=os.environ.get("WST_REMOTE_MCP_URL"),
        help="Remote MCP URL (e.g. https://host.example.com/mcp).",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.environ.get("WST_REMOTE_MCP_API_KEY"),
        help="Optional API key for protected remote MCP endpoints.",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        default=["https://readyforus.app", "https://claragurney.com"],
        help="Target URLs used for scrape and batch smoke checks.",
    )
    parser.add_argument(
        "--poll-timeout-seconds",
        type=int,
        default=120,
        help="Max seconds to wait for async job terminal state.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.remote_url:
        print("Missing --remote-url or WST_REMOTE_MCP_URL", file=sys.stderr)
        sys.exit(1)

    try:
        summary = asyncio.run(
            run_smoke_checks(
                remote_url=args.remote_url,
                api_key=args.api_key,
                targets=args.targets,
                poll_timeout_seconds=args.poll_timeout_seconds,
            )
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        sys.exit(1)

    print(json.dumps(summary, indent=2))
    sys.exit(0 if summary.get("ok") else 1)


if __name__ == "__main__":
    main()
