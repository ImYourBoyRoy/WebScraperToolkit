# ./src/web_scraper_toolkit/server/mcp_tools/forms.py
"""
Form Automation MCP Tools
=========================

Form filling, table extraction, and interactive element handling.
"""

import json
import logging

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

logger = logging.getLogger("mcp_server")


def register_form_tools(mcp, create_envelope, format_error, run_in_process):
    """Register form automation and file operation tools."""

    @mcp.tool()
    async def fill_form(
        url: str,
        fields: str,
        submit_selector: str = None,
        save_session: bool = True,
        session_name: str = "default",
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

            result = await _fill_form(
                url=url,
                fields=fields_dict,
                submit_selector=submit_selector,
                save_session=save_session,
                session_name=session_name,
            )
            return create_envelope("success", result, meta={"url": url})
        except Exception as e:
            return format_error("fill_form", e)

    @mcp.tool()
    async def extract_tables(url: str, table_selector: str = "table") -> str:
        """Extract structured table data from webpage."""
        try:
            logger.info(f"Tool Call: extract_tables {url}")
            result = await _extract_tables(url, table_selector)
            return create_envelope("success", result, meta={"url": url})
        except Exception as e:
            return format_error("extract_tables", e)

    @mcp.tool()
    async def click_element(url: str, selector: str) -> str:
        """Navigate to URL and click an element (for JS triggers, expanding sections)."""
        try:
            logger.info(f"Tool Call: click_element {selector} on {url}")
            result = await _click_element(url, selector)
            return create_envelope(
                "success", result, meta={"url": url, "selector": selector}
            )
        except Exception as e:
            return format_error("click_element", e)

    @mcp.tool()
    async def health_check() -> str:
        """Check system health. Returns status of browser, cache, sessions."""
        try:
            result = await _health_check()
            return create_envelope("success", result)
        except Exception as e:
            return format_error("health_check", e)

    @mcp.tool()
    async def validate_url(url: str) -> str:
        """Validate URL reachability before scraping. Returns status, content type, size."""
        try:
            result = await _validate_url(url)
            return create_envelope("success", result, meta={"url": url})
        except Exception as e:
            return format_error("validate_url", e)

    @mcp.tool()
    async def detect_content_type(url: str) -> str:
        """Detect content type of URL (HTML, PDF, image, etc.)."""
        try:
            result = await _detect_content_type(url)
            return create_envelope("success", result, meta={"url": url})
        except Exception as e:
            return format_error("detect_content_type", e)

    @mcp.tool()
    async def download_file(url: str, path: str) -> str:
        """Download file from URL. Saves PDFs, images, documents directly."""
        try:
            logger.info(f"Tool Call: download_file {url} -> {path}")
            result = await _download_file(url, path)
            return create_envelope("success", result, meta={"url": url, "path": path})
        except Exception as e:
            return format_error("download_file", e)

    logger.info("Registered: form/utility tools (7)")
