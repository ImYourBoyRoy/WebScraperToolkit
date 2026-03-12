# ./scripts/diag_google_matrix.py
"""
Google Strategy Matrix Diagnostic
======================================

Tests multiple browser configurations against a Google search
to identify which strategies bypass the 429 sorry/index block.
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from web_scraper_toolkit.browser.playwright_handler import PlaywrightManager  # noqa: E402

DEFAULT_URL = "https://www.google.com/search?hl=en&num=15&q=Best+open+source+web+scraping+tools+site:github.com"

class StagePlan:
    def __init__(self, name: str, description: str, config: Dict[str, Any]):
        self.name = name
        self.description = description
        self.config = config

def _build_stage_plans() -> List[StagePlan]:
    base = {
        "serp_strategy": "none",
        "serp_retry_policy": "none",
        "native_context_mode": "incognito",
        "native_profile_dir": "",
        "host_profiles_enabled": False,
        "host_learning_enabled": False,
    }

    return [
        StagePlan(
            name="chromium_headless_stealth",
            description="Playwright Chromium with stealth scripts",
            config={**base, "browser_type": "chromium", "headless": True, "stealth_mode": True, "native_fallback_policy": "off"},
        ),
        StagePlan(
            name="chromium_headless_raw",
            description="Playwright Chromium without stealth scripts",
            config={**base, "browser_type": "chromium", "headless": True, "stealth_mode": False, "native_fallback_policy": "off"},
        ),
        StagePlan(
            name="chromium_headed_stealth",
            description="Playwright Chromium headed with stealth scripts",
            config={**base, "browser_type": "chromium", "headless": False, "stealth_mode": True, "native_fallback_policy": "off"},
        ),
        StagePlan(
            name="chromium_headed_raw",
            description="Playwright Chromium headed without stealth scripts",
            config={**base, "browser_type": "chromium", "headless": False, "stealth_mode": False, "native_fallback_policy": "off"},
        ),
        StagePlan(
            name="serp_native_headless",
            description="SERP Strategy (Native Headless)",
            config={**base, "browser_type": "chromium", "headless": True, "serp_strategy": "native_first", "native_fallback_policy": "off"},
        ),
        StagePlan(
            name="serp_native_headed",
            description="SERP Strategy (Native Headed)",
            config={**base, "browser_type": "chromium", "headless": False, "serp_strategy": "native_first", "serp_retry_policy": "balanced", "native_fallback_policy": "off"},
        ),
        StagePlan(
            name="native_chrome_fallback",
            description="Toolkit native Chrome fallback",
            config={**base, "browser_type": "chrome", "headless": False, "stealth_mode": True, "native_fallback_policy": "always", "native_browser_channels": ["chrome"], "native_browser_headless": False},
        ),
        StagePlan(
            name="native_msedge_fallback",
            description="Toolkit native Edge fallback",
            config={**base, "browser_type": "chrome", "headless": False, "stealth_mode": True, "native_fallback_policy": "always", "native_browser_channels": ["msedge"], "native_browser_headless": False},
        ),
    ]

async def run_stage(plan: StagePlan, url: str) -> None:
    print(f"\n{'='*60}\nRunning Stage: {plan.name}\n{plan.description}\n{'-'*60}")
    
    start_time = time.time()
    try:
        async with PlaywrightManager(plan.config) as manager:
            content, final_url, status = await manager.smart_fetch(url, action_name=plan.name)
            elapsed = time.time() - start_time
            
            content_len = len(content) if content else 0
            is_blocked = False
            if "google.com/sorry" in (final_url or "").lower() or status in (429, 403):
                is_blocked = True
            
            print(f"Status: {status} | Elapsed: {elapsed:.1f}s | Content Len: {content_len}")
            print(f"Final URL: {final_url}")
            
            if is_blocked:
                print(">>> RESULT: BLOCKED (429 / CAPTCHA)")
            else:
                print(">>> RESULT: SUCCESS (Organic Results)")
            
    except Exception as e:
        print(f"Error executing stage {plan.name}: {e}")

async def main():
    print(f"Testing Google URL: {DEFAULT_URL}")
    stages = _build_stage_plans()
    
    for plan in stages:
        await run_stage(plan, DEFAULT_URL)

if __name__ == "__main__":
    asyncio.run(main())
