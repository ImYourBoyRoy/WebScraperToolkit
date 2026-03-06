# ./src/web_scraper_toolkit/server/mcp_tools/_management/context.py
"""
Shared context object for management tool registration helpers.
Used by config/state/job registrar modules to avoid duplicate wiring.
Run: imported during MCP tool registration only.
Inputs: MCP server instance, envelope/error callbacks, and job helpers.
Outputs: immutable context dataclass consumed by registration helpers.
Side effects: none.
Operational notes: keeps registration modules stateless and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict


@dataclass(frozen=True)
class ManagementRegistrationContext:
    mcp: Any
    create_envelope: Callable[..., str]
    format_error: Callable[[str, Exception], str]
    run_in_process: Callable[..., Awaitable[Any]]
    get_job_manager: Callable[[], Any]
    job_builder_map: Callable[[], Dict[str, Callable[[Dict[str, Any]], Awaitable[Any]]]]
