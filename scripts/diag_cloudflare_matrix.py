# ./scripts/diag_cloudflare_matrix.py
"""
Cloudflare Strategy Matrix Diagnostic
======================================

Tests multiple browser configurations against a Cloudflare Turnstile
challenge page to identify which strategies produce successful CF validation
after the solver clicks the checkbox.

Run: python scripts/diag_cloudflare_matrix.py [--url URL] [--save-artifacts]
Inputs: CLI flags, optional --url override (default: 2captcha Turnstile demo).
Outputs: console matrix table, JSON report under scripts/out/.
Side effects: launches real browser windows, clicks Turnstile checkboxes.
Operational notes: dynamic browser detection skips unavailable channels.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="    [%(name)s] %(message)s",
    stream=sys.stdout,
)

from web_scraper_toolkit.browser.playwright_handler import PlaywrightManager  # noqa: E402
from web_scraper_toolkit.diagnostics import evaluate_page_evidence  # noqa: E402

DEFAULT_URL = "https://2captcha.com/demo/cloudflare-turnstile-challenge"
OUT_DIR = PROJECT_ROOT / "scripts" / "out" / "cloudflare_matrix"


# ── Data Classes ──────────────────────────────────────────────────


@dataclass
class StagePlan:
    """Defines one browser strategy configuration to test."""

    name: str
    description: str
    config: Dict[str, Any]
    requires_channel: Optional[str] = None


@dataclass
class StageResult:
    """Result of running one stage through smart_fetch."""

    stage_index: int
    name: str
    description: str
    status: Optional[int]
    title: str
    final_url: str
    content_length: int
    elapsed_seconds: float
    turnstile_detected: bool
    solver_clicked: bool
    challenge_resolved: bool
    content_quality: str
    reason_codes: List[str]
    likely_real_page: bool
    challenge_detected: bool
    progressed: bool
    attempt_profile: str
    error: Optional[str] = None
    skipped: bool = False
    skip_reason: str = ""


# ── Helpers ───────────────────────────────────────────────────────


def _log(level: str, msg: str) -> None:
    prefix = {"*": "[*]", "+": "[+]", "-": "[-]", "!": "[!]"}.get(level, "[?]")
    print(f"{prefix} {msg}", flush=True)


def _header(text: str) -> None:
    w = 72
    print(f"\n{'═' * w}")
    print(f"  {text}")
    print(f"{'═' * w}")


async def _detect_available_channels() -> Dict[str, bool]:
    """Probe which browser channels Playwright can launch."""
    channels: Dict[str, bool] = {}
    for channel in ("chromium", "chrome", "msedge"):
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                if channel == "chromium":
                    browser = await p.chromium.launch(headless=True)
                else:
                    browser = await p.chromium.launch(headless=True, channel=channel)
                await browser.close()
                channels[channel] = True
        except Exception:
            channels[channel] = False
    return channels


def _build_stage_plans() -> List[StagePlan]:
    """Build the 8-stage strategy matrix."""

    base = {
        "serp_strategy": "none",
        "serp_retry_policy": "none",
        "native_context_mode": "incognito",
        "native_profile_dir": "",
        "host_profiles_enabled": False,
        "host_learning_enabled": False,
    }

    return [
        # 1. Playwright Chromium, headed, stealth on
        StagePlan(
            name="chromium_headed_stealth",
            description="Playwright Chromium (default) with stealth scripts",
            config={
                **base,
                "browser_type": "chromium",
                "headless": False,
                "stealth_mode": True,
                "stealth_profile": "baseline",
                "native_fallback_policy": "off",
            },
            requires_channel="chromium",
        ),
        # 2. Playwright Chromium, headed, stealth off
        StagePlan(
            name="chromium_headed_raw",
            description="Playwright Chromium without stealth (tests if stealth hurts)",
            config={
                **base,
                "browser_type": "chromium",
                "headless": False,
                "stealth_mode": False,
                "native_fallback_policy": "off",
            },
            requires_channel="chromium",
        ),
        # 3. Chrome channel, headed, stealth on
        StagePlan(
            name="chrome_headed_stealth",
            description="Chrome channel with stealth (better TLS fingerprint)",
            config={
                **base,
                "browser_type": "chrome",
                "headless": False,
                "stealth_mode": True,
                "stealth_profile": "baseline",
                "native_fallback_policy": "off",
            },
            requires_channel="chrome",
        ),
        # 4. Chrome channel, headed, stealth off
        StagePlan(
            name="chrome_headed_raw",
            description="Chrome channel without stealth scripts",
            config={
                **base,
                "browser_type": "chrome",
                "headless": False,
                "stealth_mode": False,
                "native_fallback_policy": "off",
            },
            requires_channel="chrome",
        ),
        # 5. Chrome channel, headed, clean UA/headers (diag_simple_stealth approach)
        StagePlan(
            name="chrome_headed_clean_ua",
            description="Chrome channel with patched UA + sec-ch-ua headers",
            config={
                **base,
                "browser_type": "chrome",
                "headless": False,
                "stealth_mode": False,
                "stealth_profile": "baseline",
                "native_fallback_policy": "off",
            },
            requires_channel="chrome",
        ),
        # 6. Native Chrome fallback (system binary)
        StagePlan(
            name="native_chrome_fallback",
            description="Toolkit native Chrome fallback (system Chrome binary)",
            config={
                **base,
                "browser_type": "chrome",
                "headless": False,
                "stealth_mode": True,
                "stealth_profile": "baseline",
                "native_fallback_policy": "always",
                "native_browser_channels": ["chrome"],
                "native_browser_headless": False,
            },
            requires_channel="chrome",
        ),
        # 7. Native Edge fallback
        StagePlan(
            name="native_msedge_fallback",
            description="Toolkit native Edge fallback (system Edge binary)",
            config={
                **base,
                "browser_type": "chrome",
                "headless": False,
                "stealth_mode": True,
                "stealth_profile": "baseline",
                "native_fallback_policy": "always",
                "native_browser_channels": ["msedge"],
                "native_browser_headless": False,
            },
            requires_channel="msedge",
        ),
        # 8. Headless Chrome (feasibility check)
        StagePlan(
            name="headless_chrome_stealth",
            description="Chrome channel headless with stealth (feasibility check)",
            config={
                **base,
                "browser_type": "chrome",
                "headless": True,
                "stealth_mode": True,
                "stealth_profile": "baseline",
                "native_fallback_policy": "off",
            },
            requires_channel="chrome",
        ),
    ]


# ── Stage Runner ──────────────────────────────────────────────────


async def _run_stage(
    index: int,
    plan: StagePlan,
    url: str,
    available: Dict[str, bool],
) -> StageResult:
    """Run a single strategy stage through smart_fetch."""

    # Check channel availability
    if plan.requires_channel and not available.get(plan.requires_channel, False):
        _log("-", f"SKIP {plan.name}: {plan.requires_channel} not available")
        return StageResult(
            stage_index=index,
            name=plan.name,
            description=plan.description,
            status=None,
            title="",
            final_url=url,
            content_length=0,
            elapsed_seconds=0,
            turnstile_detected=False,
            solver_clicked=False,
            challenge_resolved=False,
            content_quality="skipped",
            reason_codes=[],
            likely_real_page=False,
            challenge_detected=False,
            progressed=False,
            attempt_profile="",
            skipped=True,
            skip_reason=f"{plan.requires_channel} not available",
        )

    _log("*", f"Stage {index}: {plan.name}")
    _log("*", f"  {plan.description}")

    start = time.perf_counter()
    status: Optional[int] = None
    content = ""
    final_url = url
    metadata: Dict[str, Any] = {}
    error: Optional[str] = None

    try:
        config = {"scraper_settings": {**plan.config, "default_timeout_seconds": 90}}
        async with PlaywrightManager(config) as manager:
            content_raw, final_url, status = await manager.smart_fetch(
                url=url,
                allow_headed_retry=False,
                allow_native_fallback=plan.config.get("native_fallback_policy", "off")
                != "off",
                action_name=f"cf_matrix_{plan.name}",
            )
            content = content_raw or ""
            metadata = manager.get_last_fetch_metadata()
    except Exception as exc:
        error = str(exc)
        _log("!", f"  Error: {error}")

    elapsed = time.perf_counter() - start

    # Evaluate content quality
    evidence = evaluate_page_evidence(
        status=status,
        final_url=final_url,
        content=content,
    )

    # Check solver activity from metadata
    attempt_profile = str(metadata.get("attempt_profile", "")).strip()
    solver_clicked = "solver" in content.lower() or bool(
        metadata.get("solver_clicked", False)
    )

    # A Turnstile was detected if the solver was invoked
    turnstile_detected = bool(metadata.get("cf_solver_invoked", False))

    # Challenge resolved = we got real page content (not just a demo page)
    challenge_resolved = bool(
        evidence.likely_real_page and not evidence.challenge_detected and status == 200
    )

    result_icon = "+" if challenge_resolved else "-"
    _log(
        result_icon,
        f"  Result: status={status} chars={len(content)} "
        f"quality={evidence.content_quality} "
        f"elapsed={elapsed:.1f}s "
        f"profile={attempt_profile}",
    )

    return StageResult(
        stage_index=index,
        name=plan.name,
        description=plan.description,
        status=status,
        title=evidence.title,
        final_url=final_url,
        content_length=len(content),
        elapsed_seconds=round(elapsed, 1),
        turnstile_detected=turnstile_detected,
        solver_clicked=solver_clicked,
        challenge_resolved=challenge_resolved,
        content_quality=evidence.content_quality,
        reason_codes=evidence.reason_codes,
        likely_real_page=evidence.likely_real_page,
        challenge_detected=evidence.challenge_detected,
        progressed=evidence.progressed,
        attempt_profile=attempt_profile,
        error=error,
    )


# ── Analysis ──────────────────────────────────────────────────────


def _analyze_results(results: List[StageResult]) -> Dict[str, Any]:
    """Determine which configuration dimensions matter."""
    active = [r for r in results if not r.skipped]
    passed = [r for r in active if r.progressed]

    findings: List[str] = []
    recommendations: List[str] = []

    if not active:
        return {
            "smoking_gun": "No stages were executed.",
            "findings": [],
            "recommendations": ["Check browser availability."],
        }

    if not passed:
        return {
            "smoking_gun": "All strategies failed CF validation.",
            "findings": ["No browser configuration passed Cloudflare validation."],
            "recommendations": [
                "The test page may require real user interaction.",
                "Try running on a real CF-protected page instead.",
            ],
        }

    # Check stealth impact
    stealth_on = [r for r in active if "stealth" in r.name and r.progressed]
    stealth_off = [r for r in active if "raw" in r.name and r.progressed]
    if stealth_on and not stealth_off:
        findings.append("Stealth scripts are REQUIRED — raw configs fail.")
    elif stealth_off and not stealth_on:
        findings.append(
            "Stealth scripts HURT — raw configs succeed where stealth fails."
        )
    elif stealth_on and stealth_off:
        findings.append("Stealth mode has no impact — both work.")

    # Check browser channel impact
    chromium_results = [r for r in active if "chromium" in r.name]
    chrome_results = [
        r for r in active if "chrome" in r.name and "chromium" not in r.name
    ]
    chromium_pass = any(r.progressed for r in chromium_results)
    chrome_pass = any(r.progressed for r in chrome_results)
    if chrome_pass and not chromium_pass:
        findings.append(
            "Chrome channel succeeds where Chromium fails (TLS fingerprint)."
        )
        recommendations.append("Use browser_type='chrome' for CF-protected hosts.")
    elif chromium_pass and not chrome_pass:
        findings.append("Chromium succeeds where Chrome channel fails.")

    # Check native fallback impact
    native_pass = [r for r in active if "native" in r.name and r.progressed]
    if native_pass and not [r for r in passed if "native" not in r.name]:
        findings.append("Native browser fallback is the only working path.")
        recommendations.append("Use native_fallback_policy='always'.")

    # Check headless vs headed
    headless_results = [r for r in active if "headless" in r.name]
    headed_pass = [r for r in passed if "headless" not in r.name]
    if (
        headed_pass
        and headless_results
        and not any(r.progressed for r in headless_results)
    ):
        findings.append("Headless mode fails — headed is required.")
        recommendations.append("Keep headless=False for CF-protected hosts.")

    # Determine smoking gun
    if len(passed) == len(active):
        smoking_gun = "All strategies pass — no specific configuration required."
    elif len(passed) == 1:
        smoking_gun = f"Only '{passed[0].name}' succeeds — use this configuration."
        recommendations.append(f"Recommended profile: {passed[0].name}")
    else:
        pass_names = [r.name for r in passed]
        smoking_gun = (
            f"{len(passed)}/{len(active)} strategies pass: {', '.join(pass_names)}"
        )

    return {
        "smoking_gun": smoking_gun,
        "findings": findings,
        "recommendations": recommendations,
    }


# ── Summary Display ───────────────────────────────────────────────


def _print_matrix(results: List[StageResult], analysis: Dict[str, Any]) -> None:
    """Print the strategy matrix results as a formatted table."""
    _header("STRATEGY MATRIX RESULTS")

    # Table header
    print(
        f"\n  {'#':>2}  {'Stage':<30} {'Status':>6}  {'Time':>6}  {'Quality':<12} {'Result':<8}"
    )
    print(f"  {'─' * 2}  {'─' * 30} {'─' * 6}  {'─' * 6}  {'─' * 12} {'─' * 8}")

    for r in results:
        if r.skipped:
            icon = "⏭️"
            label = "SKIP"
        elif r.progressed:
            icon = "✅"
            label = "PASS"
        else:
            icon = "❌"
            label = "FAIL"

        status_str = str(r.status) if r.status else "—"
        time_str = f"{r.elapsed_seconds:.0f}s" if not r.skipped else "—"
        quality = r.content_quality if not r.skipped else r.skip_reason

        print(
            f"  {r.stage_index:>2}  {r.name:<30} {status_str:>6}  {time_str:>6}  "
            f"{quality:<12} {icon} {label}"
        )

    # Analysis
    _header("ANALYSIS")
    print(f"\n  🎯 {analysis['smoking_gun']}")

    if analysis.get("findings"):
        print("\n  Findings:")
        for finding in analysis["findings"]:
            print(f"    • {finding}")

    if analysis.get("recommendations"):
        print("\n  Recommendations:")
        for rec in analysis["recommendations"]:
            print(f"    → {rec}")

    # Pass rate
    active = [r for r in results if not r.skipped]
    passed = [r for r in active if r.progressed]
    print(f"\n  Pass rate: {len(passed)}/{len(active)} strategies")
    print()


# ── Artifact Persistence ──────────────────────────────────────────


def _save_report(
    results: List[StageResult],
    analysis: Dict[str, Any],
    url: str,
) -> Path:
    """Save JSON report to scripts/out/cloudflare_matrix/."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = OUT_DIR / f"run_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "target_url": url,
        "stages": [asdict(r) for r in results],
        "analysis": analysis,
        "summary": {
            "total_stages": len(results),
            "skipped": sum(1 for r in results if r.skipped),
            "passed": sum(1 for r in results if r.progressed),
            "failed": sum(1 for r in results if not r.skipped and not r.progressed),
        },
    }

    report_path = run_dir / "cf_matrix_results.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    # Also write a compact markdown summary
    md_lines = [
        f"# Cloudflare Matrix — {timestamp}",
        "",
        f"**Target:** {url}",
        "",
        "| # | Stage | Status | Time | Quality | Result |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        if r.skipped:
            md_lines.append(
                f"| {r.stage_index} | {r.name} | — | — | {r.skip_reason} | ⏭️ SKIP |"
            )
        else:
            icon = "✅" if r.progressed else "❌"
            md_lines.append(
                f"| {r.stage_index} | {r.name} | {r.status} | {r.elapsed_seconds:.0f}s | "
                f"{r.content_quality} | {icon} |"
            )
    md_lines.extend(
        [
            "",
            "## Analysis",
            "",
            f"**{analysis['smoking_gun']}**",
        ]
    )
    if analysis.get("findings"):
        md_lines.append("")
        for f in analysis["findings"]:
            md_lines.append(f"- {f}")
    if analysis.get("recommendations"):
        md_lines.append("")
        for r in analysis["recommendations"]:
            md_lines.append(f"- → {r}")

    summary_path = run_dir / "cf_matrix_summary.md"
    summary_path.write_text("\n".join(md_lines), encoding="utf-8")

    return run_dir


# ── Main ──────────────────────────────────────────────────────────


async def run_matrix(url: str, save_artifacts: bool = True) -> Dict[str, Any]:
    """Run the full CF strategy matrix and return results."""

    _header(f"CF STRATEGY MATRIX: {url}")

    # Scrub pycache
    removed = 0
    for folder in PROJECT_ROOT.rglob("__pycache__"):
        try:
            shutil.rmtree(folder, ignore_errors=True)
            removed += 1
        except Exception:
            pass
    if removed:
        _log("*", f"Scrubbed {removed} __pycache__ directories")

    # Detect available browsers
    _log("*", "Detecting available browser channels...")
    available = await _detect_available_channels()
    for channel, ok in available.items():
        icon = "✅" if ok else "❌"
        _log("*", f"  {channel}: {icon}")

    # Build and run stages
    plans = _build_stage_plans()
    results: List[StageResult] = []

    for i, plan in enumerate(plans, 1):
        result = await _run_stage(i, plan, url, available)
        results.append(result)
        print()  # visual separator between stages

    # Analyze
    analysis = _analyze_results(results)

    # Display
    _print_matrix(results, analysis)

    # Save
    if save_artifacts:
        run_dir = _save_report(results, analysis, url)
        _log("+", f"Report saved to: {run_dir}")

    return {
        "stages": [asdict(r) for r in results],
        "analysis": analysis,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cloudflare strategy matrix diagnostic"
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"Target URL (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--save-artifacts",
        action="store_true",
        default=True,
        help="Save JSON/MD reports (default: True)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Disable artifact saving",
    )
    args = parser.parse_args()

    save = args.save_artifacts and not args.no_save
    asyncio.run(run_matrix(args.url, save_artifacts=save))


if __name__ == "__main__":
    main()
