# ./src/web_scraper_toolkit/server/jobs.py
"""
Manage asynchronous MCP jobs for long-running operations with polling and cancellation.
Used by `server/mcp_tools/management.py` to expose start/poll/cancel/list job tools.
Run: Imported as a runtime service by the MCP server process.
Inputs: Coroutine workloads, timeout profiles, retention limits, and optional metadata.
Outputs: Structured job records with status, timestamps, result payload, and error details.
Side effects: Spawns asyncio tasks and keeps in-memory job state for lifecycle inspection.
Operational notes: Designed for long-running research/crawl jobs where agents should poll instead of blocking.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Dict, Optional
from uuid import uuid4

from ..core.runtime import TimeoutProfile


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class JobRecord:
    """In-memory representation of an asynchronous MCP job."""

    job_id: str
    status: str
    submitted_at: str
    timeout_profile: str
    timeout_budget: Dict[str, Any]
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    result: Any = None
    error: Optional[str] = None
    task: Optional[asyncio.Task[Any]] = None
    execution_task: Optional[asyncio.Task[Any]] = None

    def as_dict(self, include_result: bool = True) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "job_id": self.job_id,
            "status": self.status,
            "submitted_at": self.submitted_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "timeout_profile": self.timeout_profile,
            "timeout_budget": self.timeout_budget,
            "description": self.description,
            "metadata": self.metadata,
            "error": self.error,
        }
        if include_result and self.status == "completed":
            payload["result"] = self.result
        return payload


class AsyncJobManager:
    """Lifecycle manager for asynchronous jobs initiated by MCP tools."""

    def __init__(self, retention_seconds: int = 3600, max_records: int = 1000) -> None:
        self.retention_seconds = max(60, retention_seconds)
        self.max_records = max(10, max_records)
        self._jobs: Dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()

    async def submit(
        self,
        job_coro: Awaitable[Any],
        *,
        timeout_profile_name: str,
        timeout_profile: TimeoutProfile,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Submit a coroutine workload and return its job id immediately."""
        await self._cleanup()

        profile = timeout_profile.normalized()
        job_id = str(uuid4())
        record = JobRecord(
            job_id=job_id,
            status="queued",
            submitted_at=_utcnow_iso(),
            timeout_profile=timeout_profile_name,
            timeout_budget=profile.as_dict(),
            description=description,
            metadata=metadata or {},
        )

        async with self._lock:
            self._jobs[job_id] = record
            self._trim_if_needed_locked()
            record.execution_task = asyncio.ensure_future(job_coro)
            record.task = asyncio.create_task(
                self._runner(record, profile),
                name=f"mcp_job_{job_id}",
            )

        return job_id

    async def poll(self, job_id: str, include_result: bool = True) -> Dict[str, Any]:
        """Return the current state of a submitted job."""
        await self._cleanup()
        async with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return {
                    "job_id": job_id,
                    "status": "not_found",
                    "error": "Job not found or expired.",
                }
            return record.as_dict(include_result=include_result)

    async def cancel(self, job_id: str) -> Dict[str, Any]:
        """Attempt cancellation of a running or queued job."""
        async with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return {
                    "job_id": job_id,
                    "status": "not_found",
                    "cancelled": False,
                }

            cancelled = False
            if record.task and not record.task.done():
                cancelled = record.task.cancel()
            if record.execution_task and not record.execution_task.done():
                cancelled = record.execution_task.cancel() or cancelled

            if cancelled:
                record.status = "cancelled"
                record.finished_at = _utcnow_iso()
                record.error = "Cancelled by request."

            return {
                "job_id": job_id,
                "status": record.status,
                "cancelled": cancelled,
            }

    async def list_jobs(self, limit: int = 20) -> Dict[str, Any]:
        """List recent jobs, newest first."""
        await self._cleanup()
        async with self._lock:
            rows = sorted(
                self._jobs.values(),
                key=lambda item: item.submitted_at,
                reverse=True,
            )[: max(1, limit)]
            return {
                "count": len(rows),
                "jobs": [row.as_dict(include_result=False) for row in rows],
            }

    async def _runner(
        self,
        record: JobRecord,
        profile: TimeoutProfile,
    ) -> None:
        record.status = "running"
        record.started_at = _utcnow_iso()
        execution_task = record.execution_task
        if execution_task is None:
            record.status = "failed"
            record.error = "Internal job state error: missing execution task."
            record.finished_at = _utcnow_iso()
            return

        try:
            remaining_soft = max(1, profile.soft_seconds)
            result = await asyncio.wait_for(
                asyncio.shield(execution_task),
                timeout=remaining_soft,
            )
            record.result = result
            record.status = "completed"
            record.finished_at = _utcnow_iso()
            return
        except asyncio.TimeoutError:
            if not profile.allow_extension:
                await self._timeout_record(record)
                return

        try:
            extension_cap = max(0, profile.hard_seconds - profile.soft_seconds)
            extension = min(profile.extension_seconds, extension_cap)
            if extension <= 0:
                await self._timeout_record(record)
                return

            result = await asyncio.wait_for(
                asyncio.shield(execution_task),
                timeout=extension,
            )
            record.result = result
            record.status = "completed"
            record.finished_at = _utcnow_iso()
            return
        except asyncio.TimeoutError:
            await self._timeout_record(record)
            return
        except asyncio.CancelledError:
            record.status = "cancelled"
            record.error = "Cancelled by request."
            record.finished_at = _utcnow_iso()
            raise
        except Exception as exc:  # pragma: no cover - covered by caller behavior
            record.status = "failed"
            record.error = str(exc)
            record.finished_at = _utcnow_iso()
            return

    async def _timeout_record(self, record: JobRecord) -> None:
        if record.execution_task and not record.execution_task.done():
            record.execution_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await record.execution_task
        record.status = "timeout"
        record.error = "Execution timed out."
        record.finished_at = _utcnow_iso()

    async def _cleanup(self) -> None:
        async with self._lock:
            if not self._jobs:
                return
            now = datetime.now(timezone.utc)
            removal = []
            for job_id, record in self._jobs.items():
                if record.finished_at is None:
                    continue
                finished = datetime.fromisoformat(record.finished_at)
                age = (now - finished).total_seconds()
                if age > self.retention_seconds:
                    removal.append(job_id)
            for job_id in removal:
                self._jobs.pop(job_id, None)
            self._trim_if_needed_locked()

    def _trim_if_needed_locked(self) -> None:
        if len(self._jobs) <= self.max_records:
            return
        ordered = sorted(
            self._jobs.values(),
            key=lambda item: item.submitted_at,
            reverse=True,
        )
        keep_ids = {item.job_id for item in ordered[: self.max_records]}
        drop_ids = [job_id for job_id in self._jobs if job_id not in keep_ids]
        for job_id in drop_ids:
            self._jobs.pop(job_id, None)
