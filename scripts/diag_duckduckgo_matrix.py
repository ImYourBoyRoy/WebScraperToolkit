# ./scripts/diag_duckduckgo_matrix.py
"""
DuckDuckGo Strategy Matrix Diagnostic
======================================

Tests multiple browser configurations against DuckDuckGo search endpoints
(Standard JS and the HTML-only Fallback from Toolkit 0.1.7) to identify
which strategies bypass DDG's anomalous traffic bot blocks.
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
from web_scraper_toolkit.browser._playwright_handler.constants import classify_bot_block

URLS_TO_TEST = {
    "Standard JS Endpoint": "https://duckduckgo.com/?q=Best+open+source+web+scraping+tools+site%3Agithub.com&t=h_&ia=web",
    "HTML 0.1.7 Endpoint": "https://html.duckduckgo.com/html/?q=Best+open+source+web+scraping+tools+site%3Agithub.com"
}

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
            description="Toolkit native Chrome fallback (channel='chrome')",
            config={**base, "browser_type": "chrome", "headless": False, "stealth_mode": True, "native_fallback_policy": "always", "native_browser_channels": ["chrome"], "native_browser_headless": False},
        ),
    ]

async def run_stage(plan: StagePlan, url_name: str, url: str) -> None:
    print(f"\n{'='*70}\nRunning Stage: {plan.name} on {url_name}\n{plan.description}\n{'-'*70}")
    
    start_time = time.time()
    try:
        async with PlaywrightManager(plan.config) as manager:
            content, final_url, status = await manager.smart_fetch(url, action_name=plan.name)
            elapsed = time.time() - start_time
            
            content_len = len(content) if content else 0
            
            # Use our constant classifier to check if DDG blocked it
            block_reason = classify_bot_block(status=status, final_url=final_url, content_html=content)
            
            print(f"Status: {status} | Elapsed: {elapsed:.1f}s | Content Len: {content_len}")
            print(f"Final URL: {final_url}")
            
            if block_reason == "ddg_anomaly":
                print(">>> RESULT: BLOCKED (DDG Anomaly / Captcha)")
            elif status in (403, 429):
                print(f">>> RESULT: BLOCKED (HTTP {status})")
            else:
                # Basic sanity check
                if "duckduckgo.com" in (final_url or "").lower() and content_len > 1000:
                    print(">>> RESULT: SUCCESS (Organic Results Expected)")
                else:
                    print(">>> RESULT: UNKNOWN OR EMPTY RESPONSE")
            
    except Exception as e:
        print(f"Error executing stage {plan.name}: {e}")

async def main():
    stages = _build_stage_plans()
    
    for url_name, url in URLS_TO_TEST.items():
        print(f"\n\n{'*'*80}\nTESTING ENDPOINT: {url_name}\nURL: {url}\n{'*'*80}")
        for plan in stages:
            await run_stage(plan, url_name, url)

if __name__ == "__main__":
    asyncio.run(main())
