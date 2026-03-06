# ./scripts/google_stealth_check.py
"""
Live Playwright-stealth verification against Google in headless and headed modes.
Run: `python scripts/google_stealth_check.py --url https://www.google.com/`.
Inputs: CLI args (`--url`, `--profile`, `--timeout-ms`, `--output`), local Playwright install.
Outputs: JSON summary to stdout and optional artifact file under test_output.
Side effects: launches Chromium, performs outbound requests, and may create artifact files.
Operational notes: non-CI live diagnostic; best-effort evidence for request headers/fingerprint state.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from web_scraper_toolkit.browser.config import BrowserConfig
from web_scraper_toolkit.browser.playwright_handler import (
    PlaywrightManager,
    classify_bot_block,
)


async def _run_single_check(
    *,
    target_url: str,
    profile: str,
    headless: bool,
    timeout_ms: int,
) -> Dict[str, Any]:
    manager = PlaywrightManager(
        BrowserConfig(
            headless=headless,
            browser_type="chromium",
            stealth_mode=True,
            stealth_profile=profile,  # type: ignore[arg-type]
            timeout=timeout_ms,
        )
    )

    stealth_backend = (
        "stealth_class" if manager._stealth is not None else "fallback_only"
    )
    stealth_applied = False
    document_headers: Dict[str, str] = {}

    try:
        await manager.start()

        if manager._stealth is not None:
            original_apply = manager._stealth.apply_stealth_async

            async def wrapped_apply(page: Any) -> Any:
                nonlocal stealth_applied
                stealth_applied = True
                return await original_apply(page)

            manager._stealth.apply_stealth_async = wrapped_apply  # type: ignore[assignment]

        page, context = await manager.get_new_page()
        if page is None or context is None:
            return {
                "headless": headless,
                "profile": profile,
                "error": "failed_to_create_page",
                "stealth_backend": stealth_backend,
                "stealth_applied": stealth_applied,
            }

        async def _capture_document_headers(request: Any) -> None:
            nonlocal document_headers
            if request.resource_type != "document":
                return
            if "google." not in request.url:
                return
            try:
                headers = await request.all_headers()
            except Exception:
                headers = request.headers
            document_headers = dict(sorted(headers.items()))

        page.on(
            "request", lambda req: asyncio.create_task(_capture_document_headers(req))
        )

        response = await page.goto(
            target_url,
            wait_until="domcontentloaded",
            timeout=timeout_ms,
        )
        await page.wait_for_timeout(1500)

        status: Optional[int] = response.status if response else None
        final_url = page.url
        content = await page.content()
        title = await page.title()

        fingerprint = await page.evaluate(
            """() => ({
                userAgent: navigator.userAgent,
                webdriver: navigator.webdriver,
                platform: navigator.platform,
                languages: navigator.languages,
                pluginsLength: navigator.plugins ? navigator.plugins.length : null,
                hasChromeRuntime: !!(window.chrome && window.chrome.runtime),
                hardwareConcurrency: navigator.hardwareConcurrency,
                deviceMemory: navigator.deviceMemory,
                maxTouchPoints: navigator.maxTouchPoints,
                viewport: { width: window.innerWidth, height: window.innerHeight },
                screen: { width: window.screen.width, height: window.screen.height },
            })"""
        )

        result = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "target_url": target_url,
            "headless": headless,
            "profile": profile,
            "status": status,
            "final_url": final_url,
            "title": title,
            "block_reason": classify_bot_block(
                status=status,
                final_url=final_url,
                content_html=content,
            ),
            "stealth_backend": stealth_backend,
            "stealth_applied": stealth_applied,
            "document_request_headers": document_headers,
            "js_fingerprint": fingerprint,
        }

        await page.close()
        await context.close()
        return result
    finally:
        await manager.stop()


def _default_output_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Path("test_output") / f"google_stealth_check_{stamp}.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify Playwright-stealth behavior against Google in headed/headless modes."
    )
    parser.add_argument(
        "--url",
        default="https://www.google.com/",
        help="Google URL to probe (default: https://www.google.com/).",
    )
    parser.add_argument(
        "--profile",
        default="baseline",
        choices=["baseline", "experimental_serp"],
        help="Toolkit stealth profile to use for both headed/headless runs.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=60000,
        help="Navigation timeout in milliseconds.",
    )
    parser.add_argument(
        "--output",
        default=str(_default_output_path()),
        help="Artifact path for JSON output.",
    )
    return parser


async def _run(args: argparse.Namespace) -> Dict[str, Any]:
    checks = []
    for mode in (True, False):
        try:
            checks.append(
                await _run_single_check(
                    target_url=str(args.url),
                    profile=str(args.profile),
                    headless=mode,
                    timeout_ms=max(5000, int(args.timeout_ms)),
                )
            )
        except Exception as exc:  # pragma: no cover - live diagnostics
            checks.append(
                {
                    "headless": mode,
                    "profile": str(args.profile),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    payload: Dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_url": str(args.url),
        "profile": str(args.profile),
        "checks": checks,
    }
    return payload


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    payload = asyncio.run(_run(args))

    output_path = Path(str(args.output))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(json.dumps(payload, indent=2))
    print(f"\nSaved artifact: {output_path}")


if __name__ == "__main__":
    main()
