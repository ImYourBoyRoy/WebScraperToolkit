# ./src/web_scraper_toolkit/server/mcp_tools/forms.py
"""
Form Automation MCP Tools
=========================

Form filling, table extraction, and interactive element handling.
"""

import json
import logging
from typing import Optional

from ...core.automation.forms import (
    fill_form as _fill_form,
    extract_tables as _extract_tables,
    click_element as _click_element,
)
from ...core.automation.utilities import (
    health_check as _health_check,
    validate_url as _validate_url,
    detect_content_type as _detect_content_type,
    download_file as _download_file,
)
from ..handlers.config import get_runtime_config
from ..path_safety import resolve_safe_output_path

logger = logging.getLogger("mcp_server")


def register_form_tools(mcp, create_envelope, format_error, run_in_process):
    """Register form automation and file operation tools."""

    @mcp.tool()
    async def fill_form(
        url: str,
        fields: str,
        submit_selector: Optional[str] = None,
        save_session: bool = True,
        session_name: str = "default",
        timeout_profile: str = "research",
    ) -> str:
        """
        Fill and submit a web form. Supports login automation.

        Args:
            url: Page URL containing form
            fields: JSON string mapping selectors to values
                    e.g. '{"#username": "user", "#password": "pass"}'
            submit_selector: CSS selector for submit button
            save_session: Save session state after submission
            session_name: Name for saved session
        """
        try:
            logger.info(f"Tool Call: fill_form {url}")
            fields_dict = json.loads(fields) if isinstance(fields, str) else fields
            if not isinstance(fields_dict, dict):
                raise ValueError(
                    "fields must decode to a JSON object of selector/value pairs"
                )

            result = await run_in_process(
                _fill_form,
                url=url,
                fields=fields_dict,
                submit_selector=submit_selector,
                save_session=save_session,
                session_name=session_name,
                timeout_profile=timeout_profile,
                work_units=max(1, len(fields_dict)),
            )
            return create_envelope("success", result, meta={"url": url})
        except Exception as e:
            return format_error("fill_form", e)

    @mcp.tool()
    async def extract_tables(
        url: str,
        table_selector: str = "table",
        timeout_profile: str = "standard",
    ) -> str:
        """Extract structured table data from webpage."""
        try:
            logger.info(f"Tool Call: extract_tables {url}")
            result = await run_in_process(
                _extract_tables,
                url,
                table_selector,
                timeout_profile=timeout_profile,
                work_units=2,
            )
            return create_envelope("success", result, meta={"url": url})
        except Exception as e:
            return format_error("extract_tables", e)

    @mcp.tool()
    async def click_element(
        url: str,
        selector: str,
        timeout_profile: str = "standard",
    ) -> str:
        """Navigate to URL and click an element (for JS triggers, expanding sections)."""
        try:
            logger.info(f"Tool Call: click_element {selector} on {url}")
            result = await run_in_process(
                _click_element,
                url,
                selector,
                timeout_profile=timeout_profile,
                work_units=1,
            )
            return create_envelope(
                "success", result, meta={"url": url, "selector": selector}
            )
        except Exception as e:
            return format_error("click_element", e)

    @mcp.tool()
    async def health_check() -> str:
        """Check system health. Returns status of browser, cache, sessions."""
        try:
            result = await run_in_process(
                _health_check,
                timeout_profile="fast",
                work_units=1,
            )
            return create_envelope("success", result)
        except Exception as e:
            return format_error("health_check", e)

    @mcp.tool()
    async def validate_url(url: str, timeout_profile: str = "fast") -> str:
        """Validate URL reachability before scraping. Returns status, content type, size."""
        try:
            result = await run_in_process(
                _validate_url,
                url,
                timeout_profile=timeout_profile,
                work_units=1,
            )
            return create_envelope("success", result, meta={"url": url})
        except Exception as e:
            return format_error("validate_url", e)

    @mcp.tool()
    async def detect_content_type(url: str, timeout_profile: str = "fast") -> str:
        """Detect content type of URL (HTML, PDF, image, etc.)."""
        try:
            result = await run_in_process(
                _detect_content_type,
                url,
                timeout_profile=timeout_profile,
                work_units=1,
            )
            return create_envelope("success", result, meta={"url": url})
        except Exception as e:
            return format_error("detect_content_type", e)

    @mcp.tool()
    async def download_file(
        url: str,
        path: str,
        timeout_profile: str = "research",
    ) -> str:
        """Download file from URL. Saves PDFs, images, documents directly."""
        try:
            runtime = get_runtime_config()
            safe_path = resolve_safe_output_path(path, runtime.safe_output_root)
            logger.info(f"Tool Call: download_file {url} -> {safe_path}")
            result = await run_in_process(
                _download_file,
                url,
                safe_path,
                timeout_profile=timeout_profile,
                work_units=2,
            )
            return create_envelope(
                "success",
                result,
                meta={"url": url, "path": safe_path},
            )
        except Exception as e:
            return format_error("download_file", e)

    logger.info("Registered: form/utility tools (7)")
