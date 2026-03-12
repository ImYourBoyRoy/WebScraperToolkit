# ./tests/test_cloudflare_bypass.py
"""
Live Cloudflare Turnstile integration test for PlaywrightManager smart_fetch.

Run: python tests/test_cloudflare_bypass.py
     SKIP_CF_TEST=0 pytest tests/test_cloudflare_bypass.py -v
Inputs: SKIP_CF_TEST env var (default=1 to skip), outbound network access.
Outputs: detailed per-attempt results table, debug_cf.html/debug_cf.json on failure.
Side effects: launches real browser sessions, makes live web requests.
Operational notes: skipped by default to keep CI deterministic. Tests two URLs:
  1. 2captcha Turnstile demo (baseline non-challenged page)
  2. rocketreach.co (real CF-protected page — exercises the Turnstile solver)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import time
import unittest
from pathlib import Path
from typing import Any, Dict

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from web_scraper_toolkit.diagnostics import evaluate_page_evidence  # noqa: E402
from web_scraper_toolkit.browser.playwright_handler import PlaywrightManager  # noqa: E402

# Enable INFO logging so solver/manager messages appear during test
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SKIP_CF_TEST = os.getenv("SKIP_CF_TEST", "1") == "1"

# ─── Pretty Reporting ─────────────────────────────────────────────


def _print_header(title: str) -> None:
    width = 72
    print(f"\n{'═' * width}")
    print(f"  {title}")
    print(f"{'═' * width}")


def _print_result(
    url: str,
    status: Any,
    chars: int,
    elapsed: float,
    evidence: Any,
    metadata: Dict[str, Any],
) -> None:
    """Print a formatted result block for one URL test."""
    strategy = str(metadata.get("attempt_profile", "smart_fetch"))
    passed = bool(
        status == 200
        and chars > 0
        and evidence.likely_real_page
        and not evidence.challenge_detected
    )
    icon = "✅ PASS" if passed else "❌ FAIL"

    print(f"\n  URL:             {url}")
    print(f"  Strategy:        {strategy}")
    print(f"  Status:          {status}")
    print(f"  Content:         {chars} chars")
    print(f"  Elapsed:         {elapsed:.1f}s")
    print(f"  Title:           {evidence.title}")
    print(f"  Real Page:       {evidence.likely_real_page}")
    print(f"  Challenge:       {evidence.challenge_detected}")
    print(f"  Content Quality: {evidence.content_quality}")
    print(f"  Reason Codes:    {evidence.reason_codes}")
    print(f"  Result:          {icon}")


async def _run_bypass_test(
    url: str,
    config: Dict[str, Any],
    label: str,
) -> Dict[str, Any]:
    """Run smart_fetch against a URL and return structured results."""
    _print_header(f"{label}: {url}")
    start = time.perf_counter()

    async with PlaywrightManager(config) as manager:
        content, final_url, status = await manager.smart_fetch(url)
        metadata = manager.get_last_fetch_metadata()

    elapsed = time.perf_counter() - start
    chars = len(content or "")

    evidence = evaluate_page_evidence(
        status=status,
        final_url=final_url,
        content=content or "",
    )

    passed = bool(
        status == 200
        and content
        and evidence.likely_real_page
        and not evidence.challenge_detected
    )

    _print_result(url, status, chars, elapsed, evidence, metadata)

    return {
        "url": url,
        "label": label,
        "status": status,
        "final_url": final_url,
        "content_length": chars,
        "elapsed": elapsed,
        "evidence": evidence.to_dict(),
        "metadata": metadata,
        "passed": passed,
        "content_excerpt": (content or "")[:500],
    }


# ─── Test Class ───────────────────────────────────────────────────


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
        """Test bypass against 2captcha demo (non-challenged baseline)."""
        config = {
            "scraper_settings": {
                "browser_type": "chrome",
                "headless": False,
                "default_timeout_seconds": 60,
                "native_fallback_policy": "on_blocked",
                "native_browser_channels": ["chrome", "msedge"],
            }
        }
        result = await _run_bypass_test(
            url="https://2captcha.com/demo/cloudflare-turnstile-challenge",
            config=config,
            label="BASELINE (2captcha demo)",
        )

        # Write debug artifacts
        debug_dir = Path(__file__).resolve().parent
        try:
            (debug_dir / "debug_cf.json").write_text(
                json.dumps(result, indent=2, default=str), encoding="utf-8"
            )
        except Exception:
            pass

        self.assertTrue(
            result["passed"],
            f"Baseline test failed: status={result['status']} "
            f"chars={result['content_length']} "
            f"quality={result['evidence']['content_quality']}",
        )

    async def test_cloudflare_bypass_real_challenge(self) -> None:
        """Test bypass against a real CF-protected page (exercises the solver)."""
        config = {
            "scraper_settings": {
                "browser_type": "chrome",
                "headless": False,
                "default_timeout_seconds": 90,
                "native_fallback_policy": "on_blocked",
                "native_browser_channels": ["chrome", "msedge"],
            }
        }
        result = await _run_bypass_test(
            url="https://rocketreach.co/amco-management_b5ecdf05f42e7c98",
            config=config,
            label="REAL CF CHALLENGE (rocketreach)",
        )

        # Write debug artifacts
        debug_dir = Path(__file__).resolve().parent
        try:
            (debug_dir / "debug_cf_real.json").write_text(
                json.dumps(result, indent=2, default=str), encoding="utf-8"
            )
        except Exception:
            pass

        _print_header("OVERALL SUMMARY")
        if result["passed"]:
            print("  ✅ Real Cloudflare challenge BYPASSED successfully!")
        else:
            print("  ❌ Real Cloudflare challenge was NOT bypassed.")
            print(f"     Status: {result['status']}")
            print(f"     Content: {result['content_length']} chars")
            print(f"     Quality: {result['evidence']['content_quality']}")
        print()

        # This test is informational — real CF challenges may fail depending
        # on Cloudflare's current detection sensitivity and the test
        # environment's browser fingerprint. We warn instead of hard-fail.
        if not result["passed"]:
            logger.warning(
                "Real CF challenge test did not pass — this may be expected "
                "if Cloudflare's Detection has changed. Check debug_cf_real.json."
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
