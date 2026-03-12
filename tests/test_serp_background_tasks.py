# ./tests/test_serp_background_tasks.py
"""
Background-task cleanup tests for SERP request listeners.
Run with `python -m pytest -q tests/test_serp_background_tasks.py`.
Inputs: synthetic async coroutines scheduled through the internal SERP helper.
Outputs: assertions that listener tasks are drained and terminal exceptions are consumed.
Side effects: none.
Operational notes: protects against "Future exception was never retrieved" regressions
when request listeners race with page/browser teardown on protected hosts.
"""

from __future__ import annotations

import asyncio

import pytest

from web_scraper_toolkit.browser._playwright_handler.serp_attempts import (
    _track_background_task,
)


@pytest.mark.asyncio
async def test_track_background_task_consumes_terminal_exception() -> None:
    tasks: set[asyncio.Task[None]] = set()

    async def _boom() -> None:
        await asyncio.sleep(0)
        raise RuntimeError("Target page closed")

    task = _track_background_task(tasks=tasks, coro=_boom())
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)
    assert tasks == set()


@pytest.mark.asyncio
async def test_track_background_task_cancellation_cleans_registry() -> None:
    tasks: set[asyncio.Task[None]] = set()
    started = asyncio.Event()

    async def _wait_forever() -> None:
        started.set()
        await asyncio.sleep(60)

    task = _track_background_task(tasks=tasks, coro=_wait_forever())
    await started.wait()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert tasks == set()
