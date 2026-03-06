# ./src/web_scraper_toolkit/browser/_playwright_handler/native_attempts.py
"""
Native browser fallback and baseline smart-fetch attempt logic.
Used by PlaywrightManager composition for anti-bot fallback strategies.
Run: imported by browser facade.
Inputs: URLs, attempt kwargs, and manager routing/native channel settings.
Outputs: content/final_url/status tuples and metadata snapshots.
Side effects: launches native browser channels and profile directories.
Operational notes: retains legacy compatibility retry and telemetry behavior.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
from time import perf_counter
from typing import Any, Dict, Optional, Tuple, cast

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from ..serp_native import build_serp_client_hints, sanitize_headless_user_agent
from .constants import BotBlockReason, NATIVE_FALLBACK_LAUNCH_ARGS, classify_bot_block

logger = logging.getLogger("web_scraper_toolkit.browser.playwright_handler")


class PlaywrightNativeAttemptsMixin:
    async def _run_native_browser_attempt(
        self,
        *,
        url: str,
        channel: str,
        **kwargs: Any,
    ) -> Tuple[Optional[str], str, Optional[int], Dict[str, Any]]:
        """
        Execute one native-browser-channel attempt (Chrome/Edge/Chromium).

        This path intentionally uses user-installed browser channels and avoids
        playwright_stealth JS shims, relying on native browser signals plus
        minimal webdriver scrubbing.
        """
        started = perf_counter()
        final_url = url
        status: Optional[int] = None
        content: Optional[str] = None
        block_reason: BotBlockReason = "none"
        native_ua = ""
        clean_ua = ""
        temp_profile_dir = ""
        cleanup_profile_dir = False

        async with async_playwright() as playwright:
            browser: Optional[Browser] = None
            context: Optional[BrowserContext] = None
            page: Optional[Page] = None

            try:
                launch_kwargs: Dict[str, Any] = {
                    "headless": self.native_browser_headless,
                    "args": NATIVE_FALLBACK_LAUNCH_ARGS,
                    "ignore_default_args": ["--enable-automation"],
                }
                if channel != "chromium":
                    launch_kwargs["channel"] = channel

                if self.native_context_mode == "persistent":
                    temp_profile_dir, cleanup_profile_dir = (
                        self._resolve_native_profile_dir(channel)
                    )
                    context = await playwright.chromium.launch_persistent_context(
                        user_data_dir=temp_profile_dir,
                        viewport=self.default_viewport,
                        screen=self.default_viewport,
                        locale="en-US",
                        timezone_id="America/New_York",
                        java_script_enabled=True,
                        ignore_https_errors=True,
                        **cast(Any, launch_kwargs),
                    )
                    browser = context.browser
                    page = (
                        context.pages[0] if context.pages else await context.new_page()
                    )
                    try:
                        native_ua = await page.evaluate("navigator.userAgent")
                    except Exception:
                        native_ua = ""
                    clean_ua = sanitize_headless_user_agent(native_ua)
                else:
                    browser = await playwright.chromium.launch(
                        **cast(Any, launch_kwargs)
                    )
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
                        "viewport": self.default_viewport,
                        "screen": self.default_viewport,
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
                        except Exception as proxy_exc:
                            logger.warning(
                                "Native fallback (%s): proxy resolution failed (%s). Direct mode.",
                                channel,
                                proxy_exc,
                            )

                    context = await browser.new_context(**cast(Any, context_options))
                    page = await context.new_page()

                async def _route_handler(route: Any) -> None:
                    if self._is_tracker_or_ad(route.request.url):
                        await route.abort()
                        return
                    await route.continue_()

                if context is not None:
                    await context.route("**/*", _route_handler)
                    await context.add_init_script(
                        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                    )
                    await context.add_init_script(
                        """
                        Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
                        Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
                        Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});
                        """
                    )

                if page is None:
                    raise RuntimeError(
                        "Native fallback attempt failed to create a page."
                    )

                attempt_kwargs = dict(kwargs)
                attempt_kwargs.setdefault("action_name", f"native_fallback_{channel}")
                content, final_url, status = await self.fetch_page_content(
                    page,
                    url,
                    **attempt_kwargs,
                )
                is_blocked, block_reason = self._is_blocked_or_failed(
                    status=status,
                    final_url=final_url,
                    content=content,
                )
                if is_blocked:
                    logger.warning(
                        "Native fallback (%s) remained blocked: status=%s reason=%s url=%s",
                        channel,
                        status,
                        block_reason,
                        final_url,
                    )
            finally:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass
                if browser and browser.is_connected():
                    try:
                        await browser.close()
                    except Exception:
                        pass
                if cleanup_profile_dir and temp_profile_dir:
                    shutil.rmtree(temp_profile_dir, ignore_errors=True)

        metadata: Dict[str, Any] = {
            "attempt_profile": f"native_channel_{channel}",
            "stealth_engine": "native_channel",
            "status": status,
            "final_url": final_url,
            "blocked_reason": block_reason,
            "elapsed_ms": int((perf_counter() - started) * 1000),
            "native_channel": channel,
            "native_headless": self.native_browser_headless,
            "native_context_mode": self.native_context_mode,
            "ua_header": clean_ua,
            "sec_ch_ua": "",
        }
        logger.info("NATIVE_FALLBACK_ATTEMPT %s", json.dumps(metadata, sort_keys=True))
        return content, final_url, status, metadata

    async def _smart_fetch_native_fallback(
        self,
        url: str,
        **kwargs: Any,
    ) -> Tuple[Optional[str], str, Optional[int]]:
        """Try configured native browser channels in order until one is not blocked."""
        channels = self._normalized_native_channels()
        last_result: Tuple[Optional[str], str, Optional[int]] = (None, url, None)

        for channel in channels:
            try:
                (
                    content,
                    final_url,
                    status,
                    metadata,
                ) = await self._run_native_browser_attempt(
                    url=url,
                    channel=channel,
                    **kwargs,
                )
                self._last_fetch_metadata = metadata
                last_result = (content, final_url, status)
                blocked, _ = self._is_blocked_or_failed(
                    status=status,
                    final_url=final_url,
                    content=content,
                )
                if not blocked:
                    return last_result
            except Exception as exc:
                logger.warning(
                    "Native fallback channel '%s' failed: %s",
                    channel,
                    exc,
                    exc_info=True,
                )
                self._last_fetch_metadata = {
                    "attempt_profile": f"native_channel_{channel}",
                    "stealth_engine": "native_channel",
                    "status": None,
                    "final_url": url,
                    "blocked_reason": "none",
                    "elapsed_ms": 0,
                    "native_channel": channel,
                    "native_headless": self.native_browser_headless,
                    "native_context_mode": self.native_context_mode,
                    "error": str(exc),
                    "ua_header": "",
                    "sec_ch_ua": "",
                }

        return last_result

    async def _smart_fetch_standard(
        self,
        url: str,
        *,
        allow_headed_retry: bool = True,
        **kwargs: Any,
    ) -> Tuple[Optional[str], str, Optional[int]]:
        """Current baseline smart-fetch path with optional headed escalation."""
        original_stealth_mode = self.stealth_mode
        page, context = await self.get_new_page()
        if not page:
            self._last_fetch_metadata = {
                "attempt_profile": "baseline_headless"
                if self.headless
                else "baseline_headed",
                "stealth_engine": "playwright_stealth"
                if self.stealth_mode
                else "native_only",
                "status": None,
                "final_url": url,
                "blocked_reason": "none",
                "elapsed_ms": 0,
            }
            return None, url, None

        attempt_started = perf_counter()
        try:
            content, final_url, status = await self.fetch_page_content(
                page, url, **kwargs
            )
            block_reason: BotBlockReason = classify_bot_block(
                status=status,
                final_url=final_url,
                content_html=content,
            )
            is_blocked = bool(status in [403, 429] or block_reason != "none")

            self._last_fetch_metadata = {
                "attempt_profile": (
                    "baseline_headless" if self.headless else "baseline_headed"
                ),
                "stealth_engine": "playwright_stealth"
                if self.stealth_mode
                else "native_only",
                "status": status,
                "final_url": final_url,
                "blocked_reason": block_reason,
                "elapsed_ms": int((perf_counter() - attempt_started) * 1000),
                "ua_header": "",
                "sec_ch_ua": "",
            }

            if is_blocked and self.headless and allow_headed_retry:
                retry_with_native_only = bool(
                    self.stealth_mode and block_reason == "cf_challenge"
                )
                logger.warning(
                    "SmartFetch: Block detected (%s) reason=%s on %s while Headless. "
                    "Switching to HEADED mode for retry...",
                    status,
                    block_reason,
                    url,
                )
                if retry_with_native_only:
                    logger.info(
                        "SmartFetch: Using native-only headed retry for Cloudflare "
                        "challenge compatibility."
                    )

                await page.close()
                if context:
                    await context.close()
                page = None
                context = None

                await self.stop()
                self.headless = False
                if retry_with_native_only:
                    self.stealth_mode = False
                await self.start()

                page, context = await self.get_new_page()
                if page:
                    retry_started = perf_counter()
                    logger.info("SmartFetch: Retrying in Headed mode...")
                    content, final_url, status = await self.fetch_page_content(
                        page,
                        url,
                        action_name=(
                            "smart_retry_native_signals"
                            if retry_with_native_only
                            else "smart_retry"
                        ),
                        **kwargs,
                    )
                    retry_reason = classify_bot_block(
                        status=status,
                        final_url=final_url,
                        content_html=content,
                    )
                    self._last_fetch_metadata = {
                        "attempt_profile": (
                            "baseline_headed_no_stealth"
                            if not self.stealth_mode
                            else "baseline_headed"
                        ),
                        "stealth_engine": (
                            "playwright_stealth" if self.stealth_mode else "native_only"
                        ),
                        "status": status,
                        "final_url": final_url,
                        "blocked_reason": retry_reason,
                        "elapsed_ms": int((perf_counter() - retry_started) * 1000),
                        "ua_header": "",
                        "sec_ch_ua": "",
                    }
                    is_blocked = bool(status in [403, 429] or retry_reason != "none")
                    block_reason = retry_reason

            # Compatibility retry:
            # If the modern playwright_stealth stack remains blocked, retry once
            # with native-only webdriver scrubbing (legacy 0.1.7 behavior path).
            if (
                is_blocked
                and self.stealth_mode
                and allow_headed_retry
                and block_reason in {"cf_challenge", "none"}
            ):
                logger.warning(
                    "SmartFetch: Block persisted (status=%s reason=%s). "
                    "Retrying once with native-only stealth disabled.",
                    status,
                    block_reason,
                )

                if page:
                    await page.close()
                if context:
                    await context.close()
                page = None
                context = None

                await self.stop()
                self.stealth_mode = False
                if self.headless:
                    self.headless = False
                await self.start()

                page, context = await self.get_new_page()
                if page:
                    legacy_started = perf_counter()
                    content, final_url, status = await self.fetch_page_content(
                        page,
                        url,
                        action_name="smart_retry_native_signals",
                        **kwargs,
                    )
                    legacy_reason = classify_bot_block(
                        status=status,
                        final_url=final_url,
                        content_html=content,
                    )
                    self._last_fetch_metadata = {
                        "attempt_profile": (
                            "baseline_headless_no_stealth"
                            if self.headless
                            else "baseline_headed_no_stealth"
                        ),
                        "stealth_engine": "native_only",
                        "status": status,
                        "final_url": final_url,
                        "blocked_reason": legacy_reason,
                        "elapsed_ms": int((perf_counter() - legacy_started) * 1000),
                        "ua_header": "",
                        "sec_ch_ua": "",
                    }

            return content, final_url, status
        except asyncio.CancelledError:
            logger.warning("SmartFetch cancelled for %s.", url)
            raise

        finally:
            self.stealth_mode = original_stealth_mode
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            if context:
                try:
                    await context.close()
                except Exception:
                    pass

