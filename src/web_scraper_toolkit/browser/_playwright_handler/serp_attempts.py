# ./src/web_scraper_toolkit/browser/_playwright_handler/serp_attempts.py
"""
SERP native attempt execution and strategy retry ordering.
Used by PlaywrightManager smart-fetch flow for search-engine routes.
Run: imported by facade class composition.
Inputs: SERP URL/provider data and attempt profile/headless controls.
Outputs: content/final_url/status tuples plus attempt metadata.
Side effects: launches temporary Chromium sessions for native-only attempts.
Operational notes: preserves request-header and JS fingerprint debug behavior.
"""

from __future__ import annotations

import asyncio
import json
import logging
from time import perf_counter
from typing import Any, Awaitable, Dict, Literal, Optional, Set, Tuple, cast

from playwright.async_api import async_playwright

from ..serp_native import (
    build_serp_client_hints,
    is_serp_blocked,
    sanitize_headless_user_agent,
)
from .constants import (
    BotBlockReason,
    SERP_NATIVE_LAUNCH_ARGS,
    SerpProvider,
    classify_bot_block,
)

logger = logging.getLogger("web_scraper_toolkit.browser.playwright_handler")


def _track_background_task(
    *,
    tasks: Set[asyncio.Task[None]],
    coro: Awaitable[None],
) -> asyncio.Task[None]:
    """Track a fire-and-forget task and always consume its terminal result."""
    task = asyncio.create_task(coro)
    tasks.add(task)

    def _finalize(completed: asyncio.Task[None]) -> None:
        tasks.discard(completed)
        try:
            completed.result()
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.debug("SERP background task ignored exception: %s", exc)

    task.add_done_callback(_finalize)
    return task


class PlaywrightSerpAttemptsMixin:
    async def _run_serp_native_attempt(
        self,
        *,
        url: str,
        provider: Optional[SerpProvider],
        attempt_profile: Literal["native_headless", "native_headed"],
        headless: bool,
        **kwargs: Any,
    ) -> Tuple[Optional[str], str, Optional[int], Dict[str, Any]]:
        """Execute one SERP-native attempt (no playwright_stealth)."""
        started = perf_counter()
        native_ua = ""
        clean_ua = ""
        client_hints: Dict[str, str] = {}
        document_headers: Dict[str, str] = {}
        js_fingerprint: Dict[str, Any] = {}
        final_url = url
        status: Optional[int] = None
        content: Optional[str] = None
        block_reason: BotBlockReason = "none"
        request_tasks: Set[asyncio.Task[None]] = set()

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=headless,
                args=SERP_NATIVE_LAUNCH_ARGS,
                ignore_default_args=["--enable-automation"],
            )
            try:
                dummy_context = await browser.new_context()
                try:
                    dummy_page = await dummy_context.new_page()
                    native_ua = await dummy_page.evaluate("navigator.userAgent")
                finally:
                    await dummy_context.close()

                clean_ua = sanitize_headless_user_agent(native_ua)
                client_hints = build_serp_client_hints(clean_ua)

                context_options: Dict[str, Any] = {
                    "user_agent": clean_ua,
                    "viewport": {"width": 1920, "height": 1080},
                    "screen": {"width": 1920, "height": 1080},
                    "extra_http_headers": client_hints,
                    "locale": "en-US",
                    "timezone_id": "America/New_York",
                    "java_script_enabled": True,
                    "ignore_https_errors": True,
                }

                if self.proxy_manager:
                    try:
                        proxy_obj = await self.proxy_manager.get_next_proxy()
                        if proxy_obj:
                            context_options["proxy"] = (
                                self._build_playwright_proxy_settings(proxy_obj)
                            )
                    except Exception as exc:
                        logger.warning(
                            "SERP native: proxy manager resolution failed (%s). Using direct.",
                            exc,
                        )

                context = await browser.new_context(**cast(Any, context_options))
                try:
                    await context.add_init_script(
                        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                    )
                    page = await context.new_page()

                    async def _capture_document_headers(request: Any) -> None:
                        nonlocal document_headers
                        if document_headers:
                            return
                        if request.resource_type != "document":
                            return

                        lowered_url = str(request.url).lower()
                        if provider == "google_html" and "google." not in lowered_url:
                            return
                        if provider == "ddg_html" and "duckduckgo." not in lowered_url:
                            return

                        try:
                            headers = await request.all_headers()
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            headers = request.headers
                        document_headers = dict(sorted(dict(headers).items()))

                    page.on(
                        "request",
                        lambda req: _track_background_task(
                            tasks=request_tasks,
                            coro=_capture_document_headers(req),
                        ),
                    )

                    try:
                        content, final_url, status = await self.fetch_page_content(
                            page,
                            url,
                            **kwargs,
                        )
                        block_reason = classify_bot_block(
                            status=status,
                            final_url=final_url,
                            content_html=content,
                        )
                        if self.serp_debug_capture_headers:
                            js_fingerprint = await self._capture_compact_js_fingerprint(
                                page
                            )
                    finally:
                        pending_tasks = list(request_tasks)
                        for task in pending_tasks:
                            if not task.done():
                                task.cancel()
                        if pending_tasks:
                            await asyncio.gather(*pending_tasks, return_exceptions=True)
                        await page.close()
                finally:
                    await context.close()
            finally:
                await browser.close()

        metadata: Dict[str, Any] = {
            "attempt_profile": attempt_profile,
            "stealth_engine": "native_only",
            "status": status,
            "final_url": final_url,
            "blocked_reason": block_reason,
            "elapsed_ms": int((perf_counter() - started) * 1000),
            "provider": provider or "",
            "headless": headless,
            "ua_header": document_headers.get("user-agent", clean_ua),
            "sec_ch_ua": document_headers.get(
                "sec-ch-ua",
                client_hints.get("Sec-Ch-Ua", ""),
            ),
        }

        if self.serp_debug_capture_headers:
            metadata["request_headers"] = document_headers
            metadata["js_fingerprint"] = js_fingerprint

        logger.info("SERP_NATIVE_ATTEMPT %s", json.dumps(metadata, sort_keys=True))
        return content, final_url, status, metadata

    async def _smart_fetch_serp_strategy(
        self,
        url: str,
        *,
        provider: Optional[SerpProvider],
        **kwargs: Any,
    ) -> Tuple[Optional[str], str, Optional[int]]:
        """SERP strategy path with native-first fallback control."""
        if self.serp_strategy == "baseline_first":
            (
                baseline_content,
                baseline_url,
                baseline_status,
            ) = await self._smart_fetch_standard(
                url,
                allow_headed_retry=False,
                **kwargs,
            )
            if not is_serp_blocked(baseline_status, baseline_url, baseline_content):
                return baseline_content, baseline_url, baseline_status

        attempt_plan: list[tuple[Literal["native_headless", "native_headed"], bool]] = [
            ("native_headless", True),
        ]
        if self.serp_retry_policy == "balanced":
            attempt_plan.append(("native_headed", False))

        last_result: Tuple[Optional[str], str, Optional[int]] = (None, url, None)
        for idx, (attempt_profile, headless) in enumerate(attempt_plan):
            if idx > 0 and self.serp_retry_backoff_seconds > 0:
                await asyncio.sleep(self.serp_retry_backoff_seconds)

            content, final_url, status, metadata = await self._run_serp_native_attempt(
                url=url,
                provider=provider,
                attempt_profile=attempt_profile,
                headless=headless,
                **kwargs,
            )
            self._last_fetch_metadata = metadata
            last_result = (content, final_url, status)

            if not is_serp_blocked(status, final_url, content):
                return content, final_url, status

        return last_result
