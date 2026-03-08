# ./tests/test_cloudflare_bypass.py
"""
Optional live Cloudflare route integration test for PlaywrightManager smart_fetch.
Run: pytest tests/test_cloudflare_bypass.py -q
Inputs: SKIP_CF_TEST env var and outbound network access to 2captcha demo URL.
Outputs: pass/fail assertions plus debug_cf.html/debug_cf.json artifacts on failure.
Side effects: launches real browser sessions and performs live web requests.
Operational notes: skipped by default (SKIP_CF_TEST=1) to keep CI deterministic.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import unittest
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from web_scraper_toolkit.diagnostics import evaluate_page_evidence  # noqa: E402
from web_scraper_toolkit.browser.playwright_handler import PlaywrightManager  # noqa: E402

logger = logging.getLogger(__name__)

# Skip by default unless explicitly opted in for live integration runs.
SKIP_CF_TEST = os.getenv("SKIP_CF_TEST", "1") == "1"


@pytest.mark.integration
@pytest.mark.skipif(SKIP_CF_TEST, reason="Cloudflare bypass integration test disabled")
class TestCloudflareBypass(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        cache_path = Path(__file__).resolve().parent / "__pycache__"
        if cache_path.exists():
            try:
                shutil.rmtree(cache_path)
            except Exception:
                pass

    async def test_cloudflare_bypass(self) -> None:
        config = {
            "scraper_settings": {
                "browser_type": "chrome",
                "headless": False,
                "default_timeout_seconds": 60,
                "native_fallback_policy": "on_blocked",
                "native_browser_channels": ["chrome", "msedge", "chromium"],
            }
        }
        target_url = "https://2captcha.com/demo/cloudflare-turnstile-challenge"

        logger.info("Starting Cloudflare bypass test for: %s", target_url)
        metadata = {}
        verification_probe = {
            "attempted": False,
            "status": None,
            "final_url": target_url,
            "content_length": 0,
        }
        async with PlaywrightManager(config) as manager:
            content, final_url, status = await manager.smart_fetch(target_url)
            metadata = manager.get_last_fetch_metadata()
            if status == 200 and not content:
                verification_probe["attempted"] = True
                page = None
                context = None
                try:
                    page, context = await manager.get_new_page()
                    if page is not None:
                        (
                            probe_content,
                            probe_url,
                            probe_status,
                        ) = await manager.fetch_page_content(
                            page,
                            target_url,
                            action_name="cloudflare_test_registration_probe",
                            retries=0,
                            navigation_timeout_ms=45_000,
                        )
                        verification_probe.update(
                            {
                                "status": probe_status,
                                "final_url": probe_url,
                                "content_length": len(probe_content or ""),
                            }
                        )
                        if probe_content:
                            content = probe_content
                        if probe_url:
                            final_url = probe_url
                        if probe_status is not None:
                            status = probe_status
                finally:
                    if page is not None:
                        try:
                            await page.close()
                        except Exception:
                            pass
                    if context is not None:
                        try:
                            await context.close()
                        except Exception:
                            pass

        logger.info("Final status: %s", status)
        logger.info("Final URL: %s", final_url)
        logger.info("Content length: %d", len(content) if content else 0)
        logger.info("Selection metadata: %s", metadata)
        logger.info("Verification probe: %s", verification_probe)
        evidence = evaluate_page_evidence(
            status=status,
            final_url=final_url,
            content=content or "",
        )

        if (
            status == 200
            and content
            and evidence.likely_real_page
            and not evidence.challenge_detected
            and not evidence.deny_page_detected
        ):
            logger.info(
                "SUCCESS: Cloudflare bypassed and substantial content retrieved."
            )
            self.assertTrue(True)
            return

        debug_dir = Path(__file__).resolve().parent
        debug_path = debug_dir / "debug_cf.html"
        debug_meta = debug_dir / "debug_cf.json"
        try:
            debug_path.write_text(content or "", encoding="utf-8")
            debug_meta.write_text(
                json.dumps(
                    {
                        "status": status,
                        "final_url": final_url,
                        "content_length": len(content or ""),
                        "evidence": evidence.to_dict(),
                        "metadata": metadata,
                        "verification_probe": verification_probe,
                        "excerpt": (content or "")[:1000],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("Failed to write Cloudflare debug artifacts: %s", exc)

        if status == 200 and not content:
            self.fail(
                "Cloudflare route reached HTTP 200, but the test could not register "
                "DOM content even after a direct verification read. "
                "See debug_cf.json/debug_cf.html."
            )
        if status == 403:
            self.fail(
                "Cloudflare route failed with status 403. "
                "See debug_cf.json/debug_cf.html."
            )

        self.fail(
            "Cloudflare route did not register a successful real page: "
            f"status={status} content_length={len(content or '')} "
            f"challenge={evidence.challenge_detected} "
            f"deny={evidence.deny_page_detected}. "
            "See debug_cf.json/debug_cf.html."
        )


if __name__ == "__main__":
    unittest.main()
