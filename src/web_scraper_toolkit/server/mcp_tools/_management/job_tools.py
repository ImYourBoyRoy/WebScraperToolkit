# ./src/web_scraper_toolkit/server/mcp_tools/_management/job_tools.py
"""
Register async job lifecycle MCP tools for long-running operations.
Used by management facade to keep job tooling modular and testable.
Run: imported by register_management_tools during MCP startup.
Inputs: job type, JSON payload, timeout profile, and job IDs.
Outputs: envelope payloads with job IDs, status, and cancellation/list data.
Side effects: queues/cancels async jobs in the shared AsyncJobManager.
Operational notes: relies on facade-provided job manager and builder map callbacks.
"""

from __future__ import annotations

import json

from ...handlers.config import get_runtime_config
from .context import ManagementRegistrationContext


def register_job_tools(ctx: ManagementRegistrationContext) -> None:
    """Register async job management tools."""
    mcp = ctx.mcp
    create_envelope = ctx.create_envelope
    format_error = ctx.format_error
    get_job_manager = ctx.get_job_manager
    job_builder_map = ctx.job_builder_map

    @mcp.tool()
    async def start_job(
        job_type: str,
        payload_json: str,
        timeout_profile: str = "research",
    ) -> str:
        """
        Start a long-running job and return immediately with a `job_id`.

        Supported job types: `batch_scrape`, `deep_research`, `run_playbook`, `batch_contacts`.
        """
        try:
            payload = json.loads(payload_json)
            if not isinstance(payload, dict):
                raise ValueError("payload_json must decode to a JSON object")

            builders = job_builder_map()
            normalized_job_type = job_type.strip().lower()
            if normalized_job_type not in builders:
                raise ValueError(
                    f"Unsupported job_type '{job_type}'. "
                    f"Supported: {', '.join(sorted(builders.keys()))}"
                )

            runtime = get_runtime_config()
            profile = runtime.get_timeout_profile(timeout_profile)
            job_manager = get_job_manager()
            job_id = await job_manager.submit(
                builders[normalized_job_type](payload),
                timeout_profile_name=timeout_profile,
                timeout_profile=profile,
                description=f"{normalized_job_type} async job",
                metadata={"job_type": normalized_job_type},
            )
            return create_envelope(
                "success",
                {"job_id": job_id},
                meta={"job_type": normalized_job_type, "timeout_profile": timeout_profile},
            )
        except Exception as exc:
            return format_error("start_job", exc)

    @mcp.tool()
    async def poll_job(job_id: str, include_result: bool = True) -> str:
        """Get current status of a job started by `start_job`."""
        try:
            job_manager = get_job_manager()
            job_data = await job_manager.poll(job_id, include_result=include_result)
            status = "success" if job_data.get("status") != "not_found" else "error"
            return create_envelope(status, job_data, meta={"job_id": job_id})
        except Exception as exc:
            return format_error("poll_job", exc)

    @mcp.tool()
    async def cancel_job(job_id: str) -> str:
        """Cancel a running async job."""
        try:
            job_manager = get_job_manager()
            result = await job_manager.cancel(job_id)
            return create_envelope("success", result, meta={"job_id": job_id})
        except Exception as exc:
            return format_error("cancel_job", exc)

    @mcp.tool()
    async def list_jobs(limit: int = 20) -> str:
        """List recent async jobs and their statuses."""
        try:
            job_manager = get_job_manager()
            result = await job_manager.list_jobs(limit=limit)
            return create_envelope("success", result, meta={"limit": limit})
        except Exception as exc:
            return format_error("list_jobs", exc)
