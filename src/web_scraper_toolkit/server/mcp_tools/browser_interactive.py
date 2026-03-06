# ./src/web_scraper_toolkit/server/mcp_tools/browser_interactive.py
"""
Browser Interactive MCP Tools
===============================

AI-facing MCP tools for interactive browser control. Enables an AI agent to
navigate pages, click elements, fill forms, read content, take screenshots,
solve challenges, inspect accessibility trees, and run JS — all through
persistent browser sessions.

Run: Imported by mcp_server.py; not standalone.
Inputs: URLs, CSS selectors, text, JS expressions, and interaction control parameters.
Outputs: JSON envelopes with page state and content.
Side effects: drives a real browser session, triggers network requests, and can mutate remote page state.
Operational notes: tools share a persistent session across calls and enforce active-session checks for safety.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..handlers.interactive import get_interactive_session

logger = logging.getLogger("mcp_server")


def register_browser_interactive_tools(
    mcp: object,
    create_envelope: object,
    format_error: object,
    run_in_process: object,
) -> None:
    """Register AI-interactive browser tools with the MCP server."""

    @mcp.tool()
    async def browser_navigate(
        url: str,
        wait_until: str = "domcontentloaded",
    ) -> str:
        """
        Navigate the interactive browser to a URL.
        Auto-detects and solves Cloudflare and PerimeterX challenges.
        Returns page state (url, title, status).
        Creates a new session if none exists.
        """
        try:
            logger.info(f"Tool Call: browser_navigate {url}")
            session = get_interactive_session()
            state = await session.navigate(url, wait_until=wait_until)
            return create_envelope("success", state, meta={"url": url})
        except Exception as e:
            return format_error("browser_navigate", e)

    @mcp.tool()
    async def browser_click(selector: str) -> str:
        """
        Click an element on the current page by CSS selector.
        Returns updated page state after the click.
        Requires an active browser session (call browser_navigate first).
        """
        try:
            logger.info(f"Tool Call: browser_click {selector}")
            session = get_interactive_session()
            if not session.is_active:
                return create_envelope(
                    "error",
                    "No active browser session. Call browser_navigate first.",
                )
            state = await session.click(selector)
            return create_envelope("success", state, meta={"selector": selector})
        except Exception as e:
            return format_error("browser_click", e)

    @mcp.tool()
    async def browser_type(selector: str, text: str) -> str:
        """
        Type text into an input field on the current page.
        The selector should target an input, textarea, or contenteditable element.
        Returns updated page state.
        """
        try:
            logger.info(f"Tool Call: browser_type {selector}")
            session = get_interactive_session()
            if not session.is_active:
                return create_envelope(
                    "error",
                    "No active browser session. Call browser_navigate first.",
                )
            state = await session.type_text(selector, text)
            return create_envelope("success", state, meta={"selector": selector})
        except Exception as e:
            return format_error("browser_type", e)

    @mcp.tool()
    async def browser_wait_for(
        selector: Optional[str] = None,
        state: str = "visible",
        timeout_ms: int = 5000,
    ) -> str:
        """
        Wait for selector state or a fixed delay on the active page.
        Use this for SPA flows where UI updates are asynchronous.
        """
        try:
            logger.info(
                "Tool Call: browser_wait_for selector=%s state=%s timeout_ms=%s",
                selector,
                state,
                timeout_ms,
            )
            session = get_interactive_session()
            if not session.is_active:
                return create_envelope(
                    "error",
                    "No active browser session. Call browser_navigate first.",
                )
            state_payload = await session.wait_for(
                selector=selector,
                state=state,
                timeout_ms=timeout_ms,
            )
            return create_envelope("success", state_payload)
        except Exception as e:
            return format_error("browser_wait_for", e)

    @mcp.tool()
    async def browser_press_key(
        key: str,
        selector: Optional[str] = None,
        delay_ms: int = 0,
    ) -> str:
        """
        Press a keyboard key (Enter, Escape, Tab, ArrowDown, etc.).
        Optionally focus a selector before pressing.
        """
        try:
            logger.info(
                "Tool Call: browser_press_key key=%s selector=%s delay_ms=%s",
                key,
                selector,
                delay_ms,
            )
            session = get_interactive_session()
            if not session.is_active:
                return create_envelope(
                    "error",
                    "No active browser session. Call browser_navigate first.",
                )
            state_payload = await session.press_key(
                key=key,
                selector=selector,
                delay_ms=delay_ms,
            )
            return create_envelope("success", state_payload)
        except Exception as e:
            return format_error("browser_press_key", e)

    @mcp.tool()
    async def browser_scroll(
        direction: str = "down",
        amount: int = 1000,
        selector: Optional[str] = None,
        smooth: bool = True,
    ) -> str:
        """
        Scroll page content or a specific scrollable element.
        Supports directions: up, down, left, right.
        """
        try:
            logger.info(
                "Tool Call: browser_scroll direction=%s amount=%s selector=%s",
                direction,
                amount,
                selector,
            )
            session = get_interactive_session()
            if not session.is_active:
                return create_envelope(
                    "error",
                    "No active browser session. Call browser_navigate first.",
                )
            state_payload = await session.scroll(
                direction=direction,
                amount=amount,
                selector=selector,
                smooth=smooth,
            )
            return create_envelope("success", state_payload)
        except Exception as e:
            return format_error("browser_scroll", e)

    @mcp.tool()
    async def browser_hover(selector: str) -> str:
        """
        Hover over an element by CSS selector.
        Useful for menus and tooltips rendered on hover.
        """
        try:
            logger.info("Tool Call: browser_hover %s", selector)
            session = get_interactive_session()
            if not session.is_active:
                return create_envelope(
                    "error",
                    "No active browser session. Call browser_navigate first.",
                )
            state_payload = await session.hover(selector)
            return create_envelope(
                "success", state_payload, meta={"selector": selector}
            )
        except Exception as e:
            return format_error("browser_hover", e)

    @mcp.tool()
    async def browser_get_interaction_map(
        selector: Optional[str] = None,
        max_elements: int = 60,
        include_hidden: bool = False,
    ) -> str:
        """
        Return a compact map of interactive elements with selector hints.
        Optimized for LLM context windows on dynamic pages.
        """
        try:
            logger.info(
                "Tool Call: browser_get_interaction_map selector=%s max_elements=%s include_hidden=%s",
                selector,
                max_elements,
                include_hidden,
            )
            session = get_interactive_session()
            if not session.is_active:
                return create_envelope(
                    "error",
                    "No active browser session. Call browser_navigate first.",
                )
            state_payload = await session.get_interaction_map(
                selector=selector,
                max_elements=max_elements,
                include_hidden=include_hidden,
            )
            return create_envelope("success", state_payload)
        except Exception as e:
            return format_error("browser_get_interaction_map", e)

    @mcp.tool()
    async def browser_accessibility_tree(
        selector: Optional[str] = None,
        interesting_only: bool = True,
        max_nodes: int = 120,
        max_text_length: int = 160,
    ) -> str:
        """
        Return a trimmed Playwright accessibility snapshot.
        Best for role/name-driven navigation on dynamic SPAs.
        """
        try:
            logger.info(
                "Tool Call: browser_accessibility_tree selector=%s interesting_only=%s max_nodes=%s",
                selector,
                interesting_only,
                max_nodes,
            )
            session = get_interactive_session()
            if not session.is_active:
                return create_envelope(
                    "error",
                    "No active browser session. Call browser_navigate first.",
                )
            state_payload = await session.get_accessibility_tree(
                selector=selector,
                interesting_only=interesting_only,
                max_nodes=max_nodes,
                max_text_length=max_text_length,
            )
            return create_envelope("success", state_payload)
        except Exception as e:
            return format_error("browser_accessibility_tree", e)

    @mcp.tool()
    async def browser_screenshot() -> str:
        """
        Capture a screenshot of the current page.
        Returns base64-encoded PNG image data.
        """
        try:
            logger.info("Tool Call: browser_screenshot")
            session = get_interactive_session()
            if not session.is_active:
                return create_envelope(
                    "error",
                    "No active browser session. Call browser_navigate first.",
                )
            b64_img = await session.screenshot()
            return create_envelope(
                "success",
                {"image_base64": b64_img, "format": "png"},
            )
        except Exception as e:
            return format_error("browser_screenshot", e)

    @mcp.tool()
    async def browser_read_page(
        selector: Optional[str] = None,
        format: str = "text",
    ) -> str:
        """
        Read the content of the current page or a specific element.
        Format: 'text' (default), 'html'.
        Selector: Optional CSS selector to read a specific element.
        Returns page state with content field.
        """
        try:
            logger.info(
                f"Tool Call: browser_read_page selector={selector} format={format}"
            )
            session = get_interactive_session()
            if not session.is_active:
                return create_envelope(
                    "error",
                    "No active browser session. Call browser_navigate first.",
                )
            state = await session.read_page(selector=selector, format=format)
            return create_envelope("success", state)
        except Exception as e:
            return format_error("browser_read_page", e)

    @mcp.tool()
    async def browser_solve_challenge() -> str:
        """
        Explicitly trigger challenge detection and solving on the current page.
        Solves Cloudflare Turnstile, Cloudflare spatial, and PerimeterX Press & Hold.
        Returns page state with challenges_solved flag.
        """
        try:
            logger.info("Tool Call: browser_solve_challenge")
            session = get_interactive_session()
            if not session.is_active:
                return create_envelope(
                    "error",
                    "No active browser session. Call browser_navigate first.",
                )
            state = await session.solve_challenges()
            return create_envelope("success", state)
        except Exception as e:
            return format_error("browser_solve_challenge", e)

    @mcp.tool()
    async def browser_evaluate(js_expression: str) -> str:
        """
        Run a JavaScript expression on the current page and return the result.
        Useful for extracting data, checking page state, or triggering actions.
        Example: browser_evaluate("document.querySelectorAll('a').length")
        """
        try:
            logger.info("Tool Call: browser_evaluate")
            session = get_interactive_session()
            if not session.is_active:
                return create_envelope(
                    "error",
                    "No active browser session. Call browser_navigate first.",
                )
            result = await session.evaluate(js_expression)
            return create_envelope("success", {"result": result})
        except Exception as e:
            return format_error("browser_evaluate", e)

    @mcp.tool()
    async def browser_get_elements(selector: str) -> str:
        """
        Find elements matching a CSS selector on the current page.
        Returns up to 50 elements with tag, text, and href attributes.
        Useful for discovering clickable links, buttons, or form elements.
        """
        try:
            logger.info(f"Tool Call: browser_get_elements {selector}")
            session = get_interactive_session()
            if not session.is_active:
                return create_envelope(
                    "error",
                    "No active browser session. Call browser_navigate first.",
                )
            elements = await session.get_elements(selector)
            return create_envelope(
                "success",
                {"elements": elements, "count": len(elements)},
                meta={"selector": selector},
            )
        except Exception as e:
            return format_error("browser_get_elements", e)

    @mcp.tool()
    async def browser_close() -> str:
        """
        Close the interactive browser session and free resources.
        Call this when done with interactive browsing.
        """
        try:
            logger.info("Tool Call: browser_close")
            session = get_interactive_session()
            await session.close()
            return create_envelope("success", "Browser session closed.")
        except Exception as e:
            return format_error("browser_close", e)

    logger.info("Registered: browser interactive tools (15)")
