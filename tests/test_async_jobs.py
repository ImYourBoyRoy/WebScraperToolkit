# ./tests/test_async_jobs.py
"""
Test asynchronous MCP job lifecycle management (submit, poll, cancel, timeout).
"""

from __future__ import annotations

import asyncio

import pytest

from web_scraper_toolkit.core.runtime import TimeoutProfile
from web_scraper_toolkit.server.jobs import AsyncJobManager


@pytest.mark.asyncio
async def test_job_submit_and_complete() -> None:
    manager = AsyncJobManager(retention_seconds=300, max_records=100)

    async def _work() -> dict[str, str]:
        await asyncio.sleep(0.01)
        return {"status": "done"}

    job_id = await manager.submit(
        _work(),
        timeout_profile_name="fast",
        timeout_profile=TimeoutProfile(
            soft_seconds=2, hard_seconds=5, extension_seconds=1
        ),
        description="unit test completion",
    )

    for _ in range(50):
        state = await manager.poll(job_id)
        if state.get("status") == "completed":
            break
        await asyncio.sleep(0.01)

    final_state = await manager.poll(job_id)
    assert final_state["status"] == "completed"
    assert final_state["result"] == {"status": "done"}


@pytest.mark.asyncio
async def test_job_timeout() -> None:
    manager = AsyncJobManager(retention_seconds=300, max_records=100)

    async def _slow_work() -> str:
        await asyncio.sleep(1.5)
        return "slow"

    job_id = await manager.submit(
        _slow_work(),
        timeout_profile_name="fast",
        timeout_profile=TimeoutProfile(
            soft_seconds=0,
            hard_seconds=1,
            extension_seconds=0,
            allow_extension=False,
        ),
        description="unit test timeout",
    )

    for _ in range(180):
        state = await manager.poll(job_id)
        if state.get("status") in {"timeout", "completed", "failed"}:
            break
        await asyncio.sleep(0.01)

    final_state = await manager.poll(job_id)
    assert final_state["status"] == "timeout"


@pytest.mark.asyncio
async def test_job_cancel() -> None:
    manager = AsyncJobManager(retention_seconds=300, max_records=100)

    async def _work() -> None:
        await asyncio.sleep(1)

    job_id = await manager.submit(
        _work(),
        timeout_profile_name="research",
        timeout_profile=TimeoutProfile(
            soft_seconds=60, hard_seconds=120, extension_seconds=30
        ),
    )

    cancel_result = await manager.cancel(job_id)
    assert cancel_result["job_id"] == job_id

    # allow task cancellation to settle
    await asyncio.sleep(0.01)
    state = await manager.poll(job_id, include_result=False)
    assert state["status"] in {"cancelled", "running", "queued"}
