# ./tests/test_remote_mcp_integration.py
"""
Optional integration tests for a deployed remote MCP endpoint.
Run explicitly with environment variables when validating remote/server execution.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Dict

import pytest
from fastmcp import Client


REMOTE_URL = os.environ.get("WST_REMOTE_MCP_URL")
REMOTE_API_KEY = os.environ.get("WST_REMOTE_MCP_API_KEY")
TARGETS = [
    target.strip()
    for target in os.environ.get(
        "WST_REMOTE_TARGETS",
        "https://readyforus.app,https://claragurney.com",
    ).split(",")
    if target.strip()
]


def _parse_envelope(raw: str) -> Dict[str, Any]:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object envelope")
    return parsed


async def _call(client: Client, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    result = await client.call_tool(tool_name, args)
    assert not result.is_error, f"{tool_name} returned error result: {result}"
    assert isinstance(result.data, str)
    envelope = _parse_envelope(result.data)
    return envelope


pytestmark = pytest.mark.skipif(
    not REMOTE_URL,
    reason="Set WST_REMOTE_MCP_URL to enable remote integration tests.",
)


@pytest.mark.asyncio
async def test_remote_tool_registry() -> None:
    client_kwargs: Dict[str, Any] = {"timeout": 120}
    if REMOTE_API_KEY:
        client_kwargs["auth"] = REMOTE_API_KEY

    async with Client(REMOTE_URL, **client_kwargs) as client:
        tools = await client.list_tools()
        tool_names = {tool.name for tool in tools}
        for required in [
            "health_check",
            "scrape_url",
            "start_job",
            "poll_job",
            "cancel_job",
            "list_jobs",
        ]:
            assert required in tool_names


@pytest.mark.asyncio
async def test_remote_health_and_scrape() -> None:
    client_kwargs: Dict[str, Any] = {"timeout": 120}
    if REMOTE_API_KEY:
        client_kwargs["auth"] = REMOTE_API_KEY

    async with Client(REMOTE_URL, **client_kwargs) as client:
        health = await _call(client, "health_check", {})
        assert health.get("status") == "success"

        scrape = await _call(
            client,
            "scrape_url",
            {
                "url": TARGETS[0],
                "format": "markdown",
                "max_length": 2000,
                "timeout_profile": "standard",
            },
        )
        assert scrape.get("status") == "success"
        assert isinstance(scrape.get("data"), str)
        assert len(scrape.get("data", "")) > 0


@pytest.mark.asyncio
async def test_remote_async_job_flow() -> None:
    client_kwargs: Dict[str, Any] = {"timeout": 120}
    if REMOTE_API_KEY:
        client_kwargs["auth"] = REMOTE_API_KEY

    async with Client(REMOTE_URL, **client_kwargs) as client:
        payload = json.dumps({"urls": TARGETS, "format": "markdown"})
        start = await _call(
            client,
            "start_job",
            {
                "job_type": "batch_scrape",
                "payload_json": payload,
                "timeout_profile": "research",
            },
        )
        assert start.get("status") == "success"
        start_data = start.get("data", {})
        assert isinstance(start_data, dict)
        job_id = start_data.get("job_id")
        assert isinstance(job_id, str) and job_id

        deadline = time.time() + 180
        final_state = "running"
        while time.time() < deadline:
            poll = await _call(
                client,
                "poll_job",
                {"job_id": job_id, "include_result": True},
            )
            poll_data = poll.get("data", {})
            final_state = str(poll_data.get("status", "unknown"))
            if final_state in {"completed", "failed", "timeout", "cancelled"}:
                break
            await asyncio.sleep(1.0)

        assert final_state in {"completed", "failed", "timeout", "cancelled"}
