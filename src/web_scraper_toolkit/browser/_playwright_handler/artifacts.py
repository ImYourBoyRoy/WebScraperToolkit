# ./src/web_scraper_toolkit/browser/_playwright_handler/artifacts.py
"""
High-level smart-fetch orchestration and artifact capture helpers.
Used by PlaywrightManager composition for final request flow and export helpers.
Run: imported by browser facade for class composition.
Inputs: target URLs, strategy overrides, and output paths for artifacts.
Outputs: smart fetch tuples and screenshot/PDF success/status tuples.
Side effects: writes screenshot/PDF files and host profile learning telemetry.
Operational notes: final orchestration layer for split Playwright manager internals.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Mapping, Optional, Tuple

from playwright.async_api import Page

from .constants import SerpProvider
from ...diagnostics.fetch_outcome import (
    normalize_fetch_attempt,
    select_preferred_outcome,
)
from ..host_profiles import normalize_host

logger = logging.getLogger("web_scraper_toolkit.browser.playwright_handler")

if TYPE_CHECKING:
    from ..playwright_handler import PlaywrightManager


class PlaywrightSmartFetchArtifactsMixin:
    async def smart_fetch(
        self,
        url: str,
        *,
        allow_headed_retry: Optional[bool] = None,
        allow_native_fallback: Optional[bool] = None,
        provider: Optional[SerpProvider] = None,
        is_serp_request: bool = False,
        strategy_overrides: Optional[Mapping[str, Any]] = None,
        **kwargs: Any,
    ) -> Tuple[Optional[str], str, Optional[int]]:
        """
        High-level fetch with optional SERP-native strategy and baseline headed escalation.
        """
        self._last_fetch_metadata = {}
        host = normalize_host(url)
        snapshot_state = self._snapshot_routing_state()
        (
            resolved_routing,
            active_profile_applied,
            host_profile_match,
        ) = self._resolve_host_routing(
            host=host,
            strategy_overrides=strategy_overrides,
        )
        self._apply_routing_state(resolved_routing)

        effective_allow_headed_retry = (
            bool(allow_headed_retry)
            if allow_headed_retry is not None
            else bool(resolved_routing.get("allow_headed_retry", True))
        )
        if allow_headed_retry is not None:
            active_profile_applied = False
        effective_allow_native_fallback = (
            bool(allow_native_fallback) if allow_native_fallback is not None else True
        )

        result: Tuple[Optional[str], str, Optional[int]] = (None, url, None)
        try:
            if (
                effective_allow_native_fallback
                and self.native_fallback_policy == "always"
            ):
                logger.info(
                    "SmartFetch: native_fallback_policy=always for %s (channels=%s)",
                    url,
                    ",".join(self._normalized_native_channels()),
                )
                result = await self._smart_fetch_native_fallback(url, **kwargs)
                native_metadata = dict(self.get_last_fetch_metadata())
                selected = normalize_fetch_attempt(
                    content=result[0],
                    final_url=result[1],
                    status=result[2],
                    metadata=native_metadata,
                    attempt_name=str(
                        native_metadata.get("attempt_profile", "native_fallback")
                    ),
                )
                self._last_fetch_metadata = dict(selected.metadata)
                self._last_fetch_metadata["selection_reason"] = "native_policy_always"
                return result

            if self._should_use_serp_strategy(
                url=url,
                provider=provider,
                is_serp_request=is_serp_request,
            ):
                (
                    primary_content,
                    primary_url,
                    primary_status,
                ) = await self._smart_fetch_serp_strategy(
                    url,
                    provider=provider,
                    **kwargs,
                )
            else:
                (
                    primary_content,
                    primary_url,
                    primary_status,
                ) = await self._smart_fetch_standard(
                    url,
                    allow_headed_retry=effective_allow_headed_retry,
                    **kwargs,
                )

            primary_metadata = dict(self.get_last_fetch_metadata())
            selected_outcome = normalize_fetch_attempt(
                content=primary_content,
                final_url=primary_url,
                status=primary_status,
                metadata=primary_metadata,
                attempt_name=str(
                    primary_metadata.get("attempt_profile", "primary_attempt")
                ),
            )
            result = (primary_content, primary_url, primary_status)
            if effective_allow_native_fallback and self._should_attempt_native_fallback(
                status=primary_status,
                final_url=primary_url,
                content=primary_content,
            ):
                logger.info(
                    "SmartFetch: invoking native fallback after primary flow (status=%s url=%s).",
                    primary_status,
                    primary_url,
                )
                (
                    native_content,
                    native_url,
                    native_status,
                ) = await self._smart_fetch_native_fallback(
                    url,
                    **kwargs,
                )
                native_metadata = dict(self.get_last_fetch_metadata())
                native_outcome = normalize_fetch_attempt(
                    content=native_content,
                    final_url=native_url,
                    status=native_status,
                    metadata=native_metadata,
                    attempt_name=str(
                        native_metadata.get("attempt_profile", "native_fallback")
                    ),
                )
                selected_outcome = select_preferred_outcome(
                    selected_outcome,
                    native_outcome,
                )
                if selected_outcome is native_outcome:
                    logger.info(
                        "SmartFetch: native fallback selected (native_status=%s primary_status=%s).",
                        native_status,
                        primary_status,
                    )
                result = (
                    selected_outcome.content,
                    selected_outcome.final_url,
                    selected_outcome.status,
                )

            self._last_fetch_metadata = dict(selected_outcome.metadata)
            self._last_fetch_metadata["selection_reason"] = (
                "primary_preferred"
                if result
                == (
                    primary_content,
                    primary_url,
                    primary_status,
                )
                else "native_preferred"
            )

            return result
        finally:
            metadata = self._enrich_learning_metadata(host=host)
            metadata["active_host_profile_applied"] = active_profile_applied
            metadata["host_profile_match_key"] = host_profile_match.get("match_key", "")
            metadata["host_profile_match_scope"] = host_profile_match.get(
                "match_scope", "none"
            )
            metadata["host_profiles_enabled"] = self.host_profiles_enabled
            metadata["host_profiles_read_only"] = self.host_profiles_read_only
            metadata["host_learning_enabled"] = self.host_learning_enabled
            metadata["browser_launch_fallback_used"] = (
                self._browser_launch_fallback_used
            )
            metadata["resolved_routing"] = {
                **self._build_learning_routing(),
                "allow_headed_retry": effective_allow_headed_retry,
            }
            self._last_fetch_metadata = metadata

            learning_target_key = host
            learning_target_scope = "exact"
            if self._host_profile_store is not None:
                learning_target_key, learning_target_scope = (
                    self._host_profile_store.resolve_learning_target(host)
                )
            metadata["host_profile_learning_key"] = learning_target_key
            metadata["host_profile_learning_scope"] = learning_target_scope

            if (
                host
                and self.host_profiles_enabled
                and self.host_learning_enabled
                and not self.host_profiles_read_only
                and self._host_profile_store is not None
            ):
                content, final_url, status = result
                is_blocked_or_failed, block_reason = self._is_blocked_or_failed(
                    status=status,
                    final_url=final_url,
                    content=content,
                )
                try:
                    _proxy_was_used = bool(
                        getattr(self, "proxy_manager", None) is not None
                    )
                    _proxy_tier = (
                        str(
                            getattr(
                                getattr(self, "config", None),
                                "proxy_tier",
                                "",
                            )
                            or ""
                        )
                        .strip()
                        .lower()
                    )
                    self._host_profile_store.record_attempt(
                        host=learning_target_key or host,
                        scope=learning_target_scope,
                        routing=metadata["resolved_routing"],
                        success=not is_blocked_or_failed,
                        blocked_reason=block_reason,
                        context_mode=str(metadata.get("context_mode", "incognito")),
                        had_persisted_state=bool(
                            metadata.get("had_persisted_state", False)
                        ),
                        promotion_eligible=bool(
                            metadata.get("promotion_eligible", False)
                        ),
                        run_id=str(metadata.get("run_id", "")),
                        final_url=final_url,
                        status=status,
                        used_active_profile=active_profile_applied,
                        proxy_used=_proxy_was_used,
                        proxy_tier=_proxy_tier,
                    )
                except Exception as exc:
                    logger.warning(
                        "Host profile telemetry write failed for host '%s': %s",
                        host,
                        exc,
                    )

            self._restore_routing_state(snapshot_state)

    async def _auto_scroll(self, page: Page) -> None:
        """
        Scrolls the page to the bottom to trigger lazy loading.
        """
        logger.info("Auto-scrolling page to trigger lazy loading...")
        await page.evaluate(
            """
            async () => {
                await new Promise((resolve) => {
                    var totalHeight = 0;
                    var distance = 100;
                    var timer = setInterval(() => {
                        var scrollHeight = document.body.scrollHeight;
                        window.scrollBy(0, distance);
                        totalHeight += distance;

                        if(totalHeight >= scrollHeight - window.innerHeight){
                            clearInterval(timer);
                            resolve();
                        }
                    }, 100);
                });
            }
            """
        )
        await page.wait_for_timeout(2000)

    async def capture_screenshot(
        self, url: str, output_path: str, full_page: bool = True, **kwargs: Any
    ) -> Tuple[bool, Optional[int]]:
        """
        Captures a screenshot of the target URL.
        Returns: (Success, StatusCode)
        """
        page, context = await self.get_new_page()
        if not page:
            return False, None

        try:
            _, final_url, status = await self.fetch_page_content(
                page, url, action_name="loading for screenshot", **kwargs
            )

            await self._auto_scroll(page)

            logger.info("Taking screenshot of %s to %s", final_url, output_path)
            await page.screenshot(path=output_path, full_page=full_page)
            return True, status
        except Exception as e:
            logger.error("Screenshot failed: %s", e, exc_info=True)
            return False, None
        finally:
            if page:
                await page.close()
            if context:
                await context.close()

    async def save_pdf(
        self, url: str, output_path: str, **kwargs: Any
    ) -> Tuple[bool, Optional[int]]:
        """
        Saves the target URL as a PDF.
        Returns: (Success, StatusCode)
        Note: PDF generation ONLY works in HEADLESS mode in Chromium.
        """

        page, context = await self.get_new_page()
        if not page:
            return False, None

        try:
            _, _, status = await self.fetch_page_content(
                page,
                url,
                action_name="loading for PDF",
                wait_until_state="networkidle",
                **kwargs,
            )

            await self._auto_scroll(page)

            await page.emulate_media(media="screen")

            logger.info("Saving PDF of %s to %s", url, output_path)
            await page.pdf(path=output_path, format="A4", print_background=True)
            return True, status
        except Exception as e:
            logger.error("PDF generation failed: %s", e, exc_info=True)
            return False, None
        finally:
            if page:
                await page.close()
            if context:
                await context.close()

    async def __aenter__(self) -> "PlaywrightManager":
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop()
