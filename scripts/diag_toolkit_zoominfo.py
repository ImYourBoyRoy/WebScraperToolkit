# ./scripts/diag_toolkit_zoominfo.py
"""
Toolkit-native challenge diagnostic runner with stage-by-stage culprit detection.
Run: python ./scripts/diag_toolkit_zoominfo.py [--url <target_url>] [--skip-interactive] [--skip-standalone-reference] [--include-headless-stage] [--require-2xx] [--save-artifacts]
Inputs: CLI flags, toolkit BrowserConfig defaults, optional pyautogui for interactive PX solving, and optional standalone system-browser reference execution.
Outputs: Console log, ./scripts/diag_zi_result.log, and JSON report under ./scripts/out/.
Side effects: Opens real browser windows (Chromium/Chrome/Edge), may move the mouse during PX solve,
can invoke the standalone installed-Chrome/CDP reference stage, can write host profile evidence when auto-commit mode is enabled, and can write artifact bundles.
Exit codes: 0 when at least one toolkit-native stage progresses, 1 when toolkit-native stages remain blocked.
Operational notes: Testing-only diagnostics; default behavior is report-only with no profile writes.
Deterministic progression uses content/title/structure evidence, with optional strict --require-2xx gating.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import shutil
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Enable Python logging so toolkit internal messages (PX solver, interactive session)
# appear on the console alongside the diagnostic script's own output.
logging.basicConfig(
    level=logging.INFO,
    format="    [%(name)s] %(message)s",
    stream=sys.stdout,
)

try:
    from web_scraper_toolkit.browser.config import BrowserConfig
    from web_scraper_toolkit.browser.host_profiles import (
        HostProfileStore,
        normalize_host,
    )
    from web_scraper_toolkit.browser.playwright_handler import (
        _PX_CHALLENGE_MARKERS,
        PlaywrightManager,
    )
    from web_scraper_toolkit.browser.px_solver import PerimeterXSolver
    from web_scraper_toolkit.diagnostics import (
        evaluate_page_evidence,
        load_fixture,
        record_sanitized_fixture,
    )
    from web_scraper_toolkit.server.handlers.config import update_browser_config
    from web_scraper_toolkit.server.handlers.interactive import InteractiveSession
except ModuleNotFoundError:
    from web_scraper_toolkit.browser.config import BrowserConfig
    from web_scraper_toolkit.browser.host_profiles import (
        HostProfileStore,
        normalize_host,
    )
    from web_scraper_toolkit.browser.playwright_handler import (
        _PX_CHALLENGE_MARKERS,
        PlaywrightManager,
    )
    from web_scraper_toolkit.browser.px_solver import PerimeterXSolver
    from web_scraper_toolkit.diagnostics import (
        evaluate_page_evidence,
        load_fixture,
        record_sanitized_fixture,
    )
    from web_scraper_toolkit.server.handlers.config import update_browser_config
    from web_scraper_toolkit.server.handlers.interactive import InteractiveSession

TEST_URL = "https://example.com/"
HTTP_BLOCK_STATUSES = {403, 429}
LOG_FILE_HANDLE: Optional[Any] = None


@dataclass
class StagePlan:
    name: str
    description: str
    config: Dict[str, Any]
    allow_headed_retry: Optional[bool]
    allow_native_fallback: Optional[bool]
    interactive: bool = False
    standalone_reference: bool = False


@dataclass
class StageResult:
    stage_index: int
    name: str
    description: str
    started_utc: str
    ended_utc: str
    elapsed_ms: int
    status: Optional[int]
    final_url: str
    title: str
    block_reason: str
    http_blocked: bool
    challenge_detected: bool
    progressed: bool
    px_markers_found: bool
    cf_markers_found: bool
    content_length: int
    content_excerpt: str
    success_evidence: Dict[str, Any]
    metadata: Dict[str, Any]
    error: Optional[str] = None


def build_fixture_stage_result(
    *,
    fixture_path: str,
    stage_name: str = "fixture_replay",
) -> StageResult:
    """Convert a sanitized fixture into a StageResult for deterministic replay."""
    fixture = load_fixture(fixture_path)
    started = datetime.now(timezone.utc)
    eval_data = evaluate_outcome(
        status=fixture.status,
        final_url=fixture.url,
        content=fixture.html,
        title_hint=fixture.title,
    )
    ended = datetime.now(timezone.utc)
    return StageResult(
        stage_index=1,
        name=stage_name,
        description=f"Deterministic replay from fixture: {Path(fixture_path).name}",
        started_utc=started.isoformat(),
        ended_utc=ended.isoformat(),
        elapsed_ms=int((ended - started).total_seconds() * 1000),
        status=fixture.status,
        final_url=fixture.url,
        title=eval_data["title"],
        block_reason=eval_data["block_reason"],
        http_blocked=eval_data["http_blocked"],
        challenge_detected=eval_data["challenge_detected"],
        progressed=eval_data["progressed"],
        px_markers_found=eval_data["px_markers_found"],
        cf_markers_found=eval_data["cf_markers_found"],
        content_length=eval_data["content_length"],
        content_excerpt=fixture.html[:4000],
        success_evidence=eval_data["success_evidence"],
        metadata={
            "fixture_replay_path": str(Path(fixture_path).resolve()),
            "fixture_name": fixture.fixture_name,
            "tool_source": fixture.tool_source,
            "status_source": "fixture_replay",
            "expected_evidence": fixture.expected_evidence,
        },
        error=None,
    )


def log(level: str, message: str) -> None:
    prefix = {
        "+": "[+]",
        "-": "[-]",
        "*": "[*]",
        "!": "[!]",
    }.get(level, "[?]")
    line = f"{prefix} {message}"
    print(line, flush=True)
    if LOG_FILE_HANDLE is not None:
        LOG_FILE_HANDLE.write(line + "\n")
        LOG_FILE_HANDLE.flush()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def slugify_name(value: str) -> str:
    """Convert arbitrary names into stable filesystem-safe slugs."""
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip().lower())
    return cleaned.strip("._-") or "stage"


def write_stage_artifacts(
    *,
    artifacts_root: Path,
    run_id: str,
    stage_result: StageResult,
) -> Dict[str, str]:
    """Persist per-stage diagnostic artifacts for post-run auditability."""
    stage_slug = slugify_name(stage_result.name)
    stage_dir = artifacts_root / run_id / f"{stage_result.stage_index:02d}_{stage_slug}"
    stage_dir.mkdir(parents=True, exist_ok=True)

    stage_json_path = stage_dir / "stage_result.json"
    stage_json_path.write_text(
        json.dumps(asdict(stage_result), indent=2), encoding="utf-8"
    )

    excerpt_path = stage_dir / "content_excerpt.html"
    if stage_result.content_excerpt.strip():
        excerpt_path.write_text(stage_result.content_excerpt, encoding="utf-8")

    manifest = {
        "stage_dir": str(stage_dir.resolve()),
        "stage_json_path": str(stage_json_path.resolve()),
    }
    if excerpt_path.exists():
        manifest["content_excerpt_path"] = str(excerpt_path.resolve())
    return manifest


def scrub_pycache(root: Path) -> int:
    removed = 0
    for folder in root.rglob("__pycache__"):
        shutil.rmtree(folder, ignore_errors=True)
        removed += 1
    return removed


def extract_title_from_html(content: str) -> str:
    match = re.search(
        r"<title[^>]*>(.*?)</title>", content, flags=re.IGNORECASE | re.DOTALL
    )
    if not match:
        return ""
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return title


def has_markers(content: str, markers: tuple[str, ...]) -> bool:
    lowered = content.lower()
    return any(marker in lowered for marker in markers)


def count_marker_hits(content: str, markers: tuple[str, ...]) -> int:
    lowered = content.lower()
    return sum(lowered.count(marker) for marker in markers)


def estimate_text_word_count(content: str) -> int:
    text = re.sub(r"<[^>]+>", " ", content)
    return len(re.findall(r"[a-zA-Z]{3,}", text))


def count_structure_signals(content: str) -> int:
    lowered = content.lower()
    signals = [
        "<main",
        "<h1",
        "<h2",
        "<article",
        "<section",
        "<footer",
        "application/ld+json",
        "og:title",
        "twitter:title",
        "schema.org",
    ]
    return sum(1 for signal in signals if signal in lowered)


def url_has_challenge_pattern(url: str) -> bool:
    lowered = (url or "").lower()
    return "__cf_chl" in lowered or "captcha" in lowered or "challenge" in lowered


async def probe_page_status(session: InteractiveSession) -> Optional[int]:
    """Best-effort status probe for the currently loaded document URL."""
    try:
        probed = await session.evaluate(
            """
            async () => {
                try {
                    const response = await fetch(window.location.href, {
                        method: "GET",
                        credentials: "include",
                        cache: "no-store"
                    });
                    return Number.isFinite(response.status) ? response.status : null;
                } catch (error) {
                    return null;
                }
            }
            """
        )
        if isinstance(probed, int):
            return probed
    except Exception:
        return None
    return None


def evaluate_outcome(
    *,
    status: Optional[int],
    final_url: str,
    content: str,
    title_hint: str = "",
    require_2xx_status: bool = False,
) -> Dict[str, Any]:
    evidence = evaluate_page_evidence(
        status=status,
        final_url=final_url,
        content=content,
        title_hint=title_hint,
        require_2xx_status=require_2xx_status,
    )

    success_evidence = {
        "likely_real_page": evidence.likely_real_page,
        "title_challenge": evidence.title_challenge,
        "deny_page_detected": evidence.deny_page_detected,
        "visible_text_length": evidence.visible_text_length,
        "word_count_estimate": evidence.visible_word_count,
        "structure_signal_count": evidence.structure_signal_count,
        "rich_content_length": evidence.rich_content_length,
        "marker_hits_total": evidence.marker_hits_total,
        "marker_density": evidence.marker_density,
        "marker_soft_signal_only": evidence.marker_soft_signal_only,
        "require_2xx_status": require_2xx_status,
        "status_is_2xx": evidence.status_is_2xx,
        "strict_status_gate_failed": evidence.strict_status_gate_failed,
        "content_quality": evidence.content_quality,
        "reason_codes": evidence.reason_codes,
        "stale_http_status_ignored": bool(
            status in HTTP_BLOCK_STATUSES and evidence.likely_real_page
        ),
    }
    return {
        "title": evidence.title,
        "block_reason": evidence.block_reason,
        "http_blocked": bool(
            status in HTTP_BLOCK_STATUSES and not evidence.likely_real_page
        ),
        "challenge_detected": evidence.challenge_detected,
        "progressed": evidence.progressed,
        "px_markers_found": evidence.px_markers_found,
        "cf_markers_found": evidence.cf_markers_found,
        "content_length": evidence.content_length,
        "success_evidence": success_evidence,
    }


def is_reference_stage_name(name: str) -> bool:
    """Identify non-toolkit reference stages that validate external runtime behavior."""
    return name.startswith("standalone_system_")


def is_reference_stage_result(result: StageResult) -> bool:
    """Return True when the stage is a standalone reference rather than toolkit flow."""
    if bool(result.metadata.get("reference_only", False)):
        return True
    return is_reference_stage_name(result.name)


async def run_playwright_stage(
    stage_index: int,
    plan: StagePlan,
    url: str,
    timeout_ms: int,
    require_2xx_status: bool,
) -> StageResult:
    started = datetime.now(timezone.utc)
    manager = PlaywrightManager(config=BrowserConfig.from_dict(plan.config))
    status: Optional[int] = None
    final_url = url
    content = ""
    metadata: Dict[str, Any] = {}
    error: Optional[str] = None

    try:
        content_raw, final_url, status = await manager.smart_fetch(
            url=url,
            allow_headed_retry=plan.allow_headed_retry,
            allow_native_fallback=plan.allow_native_fallback,
            action_name=f"toolkit_stage_{plan.name}",
            navigation_timeout_ms=timeout_ms,
        )
        content = content_raw or ""
        metadata = manager.get_last_fetch_metadata()
        metadata.setdefault("status_source", "playwright_navigation_response")
        metadata.setdefault("strict_status_required", bool(require_2xx_status))
    except Exception as exc:
        error = str(exc)
    finally:
        try:
            await manager.stop()
        except Exception:
            pass

    ended = datetime.now(timezone.utc)
    metadata.setdefault("status_source", "playwright_navigation_response")
    metadata.setdefault("strict_status_required", bool(require_2xx_status))
    eval_data = evaluate_outcome(
        status=status,
        final_url=final_url,
        content=content,
        require_2xx_status=require_2xx_status,
    )
    return StageResult(
        stage_index=stage_index,
        name=plan.name,
        description=plan.description,
        started_utc=started.isoformat(),
        ended_utc=ended.isoformat(),
        elapsed_ms=int((ended - started).total_seconds() * 1000),
        status=status,
        final_url=final_url,
        title=eval_data["title"],
        block_reason=eval_data["block_reason"],
        http_blocked=eval_data["http_blocked"],
        challenge_detected=eval_data["challenge_detected"],
        progressed=eval_data["progressed"],
        px_markers_found=eval_data["px_markers_found"],
        cf_markers_found=eval_data["cf_markers_found"],
        content_length=eval_data["content_length"],
        content_excerpt=content[:4000],
        success_evidence=eval_data["success_evidence"],
        metadata=metadata,
        error=error,
    )


async def run_standalone_reference_stage(
    stage_index: int,
    plan: StagePlan,
    url: str,
    timeout_ms: int,
    require_2xx_status: bool,
) -> StageResult:
    """Run the standalone system-browser CDP diagnostic as a reference stage."""
    started = datetime.now(timezone.utc)
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "diag_zoominfo_bypass.py"),
        "--browser",
        "chrome",
        "--url",
        url,
    ]
    stdout_text = ""
    stderr_text = ""
    error: Optional[str] = None
    return_code: Optional[int] = None

    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(PROJECT_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        timeout_seconds = max(90, int(timeout_ms / 1000) + 60)
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            proc.kill()
            stdout_bytes, stderr_bytes = await proc.communicate()
            error = f"Standalone reference timed out after {timeout_seconds}s."
        return_code = proc.returncode
        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")
    except Exception as exc:
        error = str(exc)

    combined_output = "\n".join(
        chunk for chunk in [stdout_text.strip(), stderr_text.strip()] if chunk
    ).strip()
    title_match = re.search(r"^Title\s*:\s*(.+)$", combined_output, flags=re.MULTILINE)
    url_match = re.search(r"^URL\s*:\s*(.+)$", combined_output, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else ""
    final_url = url_match.group(1).strip() if url_match else url

    lowered_output = combined_output.lower()
    success_marker = (
        "bypass successful" in lowered_output or "real page loaded" in lowered_output
    )
    title_lower = title.lower()
    challenge_detected = bool(
        not success_marker
        and (
            "failed to bypass target site" in lowered_output
            or "challenge solving loop timed out" in lowered_output
            or "just a moment" in title_lower
            or "access denied" in title_lower
            or "press & hold" in lowered_output
        )
    )
    deny_page_detected = bool(
        "access to this page has been denied" in title_lower
        or "access denied" in title_lower
    )
    status = 200 if success_marker else None
    if deny_page_detected:
        status = 403

    strict_status_gate_failed = bool(require_2xx_status and status != 200)
    progressed = bool(success_marker and not strict_status_gate_failed)
    success_evidence = {
        "likely_real_page": progressed,
        "title_challenge": bool(
            "just a moment" in title_lower or "access denied" in title_lower
        ),
        "deny_page_detected": deny_page_detected,
        "visible_text_length": 0,
        "word_count_estimate": 0,
        "structure_signal_count": 0,
        "rich_content_length": False,
        "marker_hits_total": 0,
        "marker_density": 0.0,
        "marker_soft_signal_only": False,
        "require_2xx_status": require_2xx_status,
        "status_is_2xx": status == 200,
        "strict_status_gate_failed": strict_status_gate_failed,
        "content_quality": "reference_success" if progressed else "reference_failed",
        "reason_codes": (
            ["standalone_success_signal"]
            if progressed
            else ["standalone_reference_failed"]
        ),
        "stale_http_status_ignored": False,
        "runtime_channel": "system_browser_cdp",
    }
    ended = datetime.now(timezone.utc)
    metadata = {
        "status_source": "standalone_reference_stdout",
        "strict_status_required": bool(require_2xx_status),
        "attempt_profile": "standalone_system_chrome_reference",
        "reference_only": True,
        "runtime_channel": "system_browser_cdp",
        "browser_channel": "chrome",
        "context_mode": "temp_profile_incognito",
        "subprocess_return_code": return_code,
        "command": command,
        "stdout_excerpt": stdout_text[:2000],
        "stderr_excerpt": stderr_text[:1000],
    }
    return StageResult(
        stage_index=stage_index,
        name=plan.name,
        description=plan.description,
        started_utc=started.isoformat(),
        ended_utc=ended.isoformat(),
        elapsed_ms=int((ended - started).total_seconds() * 1000),
        status=status,
        final_url=final_url,
        title=title,
        block_reason="none" if progressed else "standalone_reference_failed",
        http_blocked=bool(status in HTTP_BLOCK_STATUSES),
        challenge_detected=challenge_detected,
        progressed=progressed,
        px_markers_found=False,
        cf_markers_found=False,
        content_length=0,
        content_excerpt=combined_output[:4000],
        success_evidence=success_evidence,
        metadata=metadata,
        error=error,
    )


def _pick_autocommit_stage(stage_results: List[StageResult]) -> Optional[StageResult]:
    preferred_order = [
        "toolkit_native_chrome_default",
        "interactive_session_chrome",
        "baseline_chrome_headed_only",
        "baseline_chrome_headless_safety_check",
    ]
    by_name = {stage.name: stage for stage in stage_results}
    for name in preferred_order:
        stage = by_name.get(name)
        if not stage or not stage.progressed:
            continue
        routing = stage.metadata.get("resolved_routing")
        if isinstance(routing, dict) and routing:
            return stage
    return None


def _normalized_learning_routing(stage: StageResult) -> Dict[str, Any]:
    raw = stage.metadata.get("resolved_routing")
    routing = dict(raw) if isinstance(raw, dict) else {}
    policy = str(routing.get("native_fallback_policy", "on_blocked")).strip().lower()
    if policy not in {"off", "on_blocked"}:
        routing["native_fallback_policy"] = "on_blocked"
    return routing


async def _verify_clean_incognito(
    *,
    url: str,
    timeout_ms: int,
    routing: Dict[str, Any],
    require_2xx_status: bool,
) -> Dict[str, Any]:
    verify_cfg = BrowserConfig.from_dict(
        {
            "browser_type": "chrome",
            "headless": False,
            "stealth_mode": True,
            "stealth_profile": "baseline",
            "serp_strategy": "none",
            "serp_retry_policy": "none",
            "native_context_mode": "incognito",
            "native_profile_dir": "",
            "native_fallback_policy": "on_blocked",
            "native_browser_channels": ["chrome", "msedge", "chromium"],
            "host_profiles_enabled": False,
            "host_profiles_read_only": True,
            "host_learning_enabled": False,
        }
    )
    manager = PlaywrightManager(config=verify_cfg)
    status: Optional[int] = None
    final_url = url
    content = ""
    error = ""
    try:
        content_raw, final_url, status = await manager.smart_fetch(
            url=url,
            allow_headed_retry=bool(routing.get("allow_headed_retry", False)),
            allow_native_fallback=True,
            strategy_overrides=routing,
            action_name="autocommit_verify_clean_incognito",
            navigation_timeout_ms=timeout_ms,
        )
        content = content_raw or ""
    except Exception as exc:
        error = str(exc)
    finally:
        try:
            await manager.stop()
        except Exception:
            pass
    outcome = evaluate_outcome(
        status=status,
        final_url=final_url,
        content=content,
        require_2xx_status=require_2xx_status,
    )
    if outcome["progressed"]:
        return {
            "status": status,
            "final_url": final_url,
            "block_reason": outcome["block_reason"],
            "progressed": outcome["progressed"],
            "success_evidence": outcome["success_evidence"],
            "error": error,
            "verification_mode": "smart_fetch",
        }

    interactive_result = await run_interactive_stage(
        stage_index=0,
        plan=StagePlan(
            name="autocommit_verify_interactive",
            description="Auto-commit verification interactive fallback.",
            config={},
            allow_headed_retry=None,
            allow_native_fallback=None,
            interactive=True,
        ),
        url=url,
        require_2xx_status=require_2xx_status,
    )
    return {
        "status": interactive_result.status,
        "final_url": interactive_result.final_url,
        "block_reason": interactive_result.block_reason,
        "progressed": interactive_result.progressed,
        "success_evidence": interactive_result.success_evidence,
        "error": error or interactive_result.error or "",
        "verification_mode": "interactive_fallback",
    }


async def _autocommit_host_profile(
    *,
    url: str,
    timeout_ms: int,
    stage_results: List[StageResult],
    enabled: bool,
    host_profiles_path: str,
    read_only: bool,
    require_2xx_status: bool,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "autocommit_attempted": False,
        "autocommit_verified": False,
        "autocommit_written": False,
        "autocommit_reason": "disabled",
        "autocommit_target_host_key": "",
        "autocommit_target_scope": "none",
        "autocommit_source_stage": "",
    }
    if not enabled:
        return result

    result["autocommit_attempted"] = True
    if read_only:
        result["autocommit_reason"] = "read_only_enabled"
        return result

    winner = _pick_autocommit_stage(stage_results)
    if winner is None:
        result["autocommit_reason"] = "no_progressed_stage_with_routing"
        return result

    routing = _normalized_learning_routing(winner)
    if not routing:
        result["autocommit_reason"] = "empty_routing_payload"
        return result
    result["autocommit_source_stage"] = winner.name

    verification = await _verify_clean_incognito(
        url=url,
        timeout_ms=timeout_ms,
        routing=routing,
        require_2xx_status=require_2xx_status,
    )
    result["verification"] = verification
    if not bool(verification.get("progressed")):
        result["autocommit_reason"] = "verification_failed"
        return result

    result["autocommit_verified"] = True
    host_key = normalize_host(url)
    if not host_key:
        result["autocommit_reason"] = "invalid_host"
        return result

    store = HostProfileStore(path=host_profiles_path)
    target_key, target_scope = store.resolve_learning_target(host_key)
    result["autocommit_target_host_key"] = target_key
    result["autocommit_target_scope"] = target_scope

    # Record two clean incognito successes: winning observation + clean verification.
    base_run_id = datetime.now(timezone.utc).strftime("autocommit_%Y%m%dT%H%M%S%fZ")
    store.record_attempt(
        host=target_key,
        scope=target_scope,
        routing=routing,
        success=True,
        blocked_reason="none",
        context_mode="incognito",
        had_persisted_state=False,
        promotion_eligible=True,
        run_id=f"{base_run_id}_observed",
        final_url=winner.final_url,
        status=winner.status,
        used_active_profile=False,
    )
    store.record_attempt(
        host=target_key,
        scope=target_scope,
        routing=routing,
        success=True,
        blocked_reason="none",
        context_mode="incognito",
        had_persisted_state=False,
        promotion_eligible=True,
        run_id=f"{base_run_id}_verify",
        final_url=str(verification.get("final_url", url)),
        status=verification.get("status"),
        used_active_profile=False,
    )
    snapshot = store.export_profiles(host=target_key)
    host_record = snapshot.get("hosts", {}).get(target_key, {})
    result["autocommit_snapshot"] = host_record
    result["autocommit_written"] = bool(host_record)
    result["autocommit_reason"] = "written_after_clean_verification"
    return result


async def run_interactive_stage(
    stage_index: int,
    plan: StagePlan,
    url: str,
    require_2xx_status: bool,
) -> StageResult:
    started = datetime.now(timezone.utc)
    session = InteractiveSession()
    status: Optional[int] = None
    final_url = url
    content = ""
    error: Optional[str] = None
    status_source = "unavailable"
    initial_status: Optional[int] = None

    try:
        update_browser_config(
            headless=False,
            interactive_channel="chrome",
            interactive_context_mode="incognito",
            native_context_mode="incognito",
        )

        state = await session.navigate(url)
        status = state.get("status")
        initial_status = state.get("initial_status")
        final_url = str(state.get("url", url))
        if isinstance(status, int):
            status_source = str(
                state.get("status_source", "interactive_navigate_state")
            )

        html_state = await session.read_page(format="html")
        content = str(html_state.get("content", ""))
        read_state_status = html_state.get("status")
        if isinstance(read_state_status, int):
            status = read_state_status
            status_source = str(
                html_state.get("status_source", "interactive_read_page_state")
            )
        if status is None:
            probed_status = await probe_page_status(session)
            if isinstance(probed_status, int):
                status = probed_status
                status_source = "interactive_js_fetch_probe"

        if has_markers(content, _PX_CHALLENGE_MARKERS) and len(content) < 50000:
            if PerimeterXSolver.is_available():
                log(
                    "*",
                    "Interactive stage: PX markers still present, retrying solve_challenges().",
                )
                await session.solve_challenges()
                state_after = await session.read_page(format="html")
                content = str(state_after.get("content", ""))
                final_url = str(state_after.get("url", final_url))
                post_solve_status = state_after.get("status")
                if isinstance(post_solve_status, int):
                    status = post_solve_status
                    status_source = str(
                        state_after.get(
                            "status_source",
                            "interactive_post_solve_read_page",
                        )
                    )
                elif status is None:
                    probed_status = await probe_page_status(session)
                    if isinstance(probed_status, int):
                        status = probed_status
                        status_source = "interactive_post_solve_js_fetch_probe"
            else:
                log(
                    "!",
                    "Interactive stage: pyautogui unavailable, PX hold cannot be auto-solved.",
                )
    except Exception as exc:
        error = str(exc)
    finally:
        try:
            await session.close()
        except Exception:
            pass

    ended = datetime.now(timezone.utc)
    eval_data = evaluate_outcome(
        status=status,
        final_url=final_url,
        content=content,
        require_2xx_status=require_2xx_status,
    )
    metadata = {
        "status_source": status_source,
        "strict_status_required": bool(require_2xx_status),
        "attempt_profile": "interactive_session_chrome",
        "context_mode": "incognito",
        "interactive_channel": "chrome",
        "px_solver_available": PerimeterXSolver.is_available(),
        "initial_status": initial_status,
    }
    return StageResult(
        stage_index=stage_index,
        name=plan.name,
        description=plan.description,
        started_utc=started.isoformat(),
        ended_utc=ended.isoformat(),
        elapsed_ms=int((ended - started).total_seconds() * 1000),
        status=status,
        final_url=final_url,
        title=eval_data["title"],
        block_reason=eval_data["block_reason"],
        http_blocked=eval_data["http_blocked"],
        challenge_detected=eval_data["challenge_detected"],
        progressed=eval_data["progressed"],
        px_markers_found=eval_data["px_markers_found"],
        cf_markers_found=eval_data["cf_markers_found"],
        content_length=eval_data["content_length"],
        content_excerpt=content[:4000],
        success_evidence=eval_data["success_evidence"],
        metadata=metadata,
        error=error,
    )


def build_stage_plans(
    skip_interactive: bool,
    include_headless_stage: bool,
    skip_standalone_reference: bool,
) -> List[StagePlan]:
    baseline_common = {
        "browser_type": "chrome",
        "headless": False,
        "stealth_mode": True,
        "stealth_profile": "baseline",
        "serp_strategy": "none",
        "serp_retry_policy": "none",
        "serp_allowlist_only": True,
        "serp_debug_capture_headers": False,
        "native_context_mode": "incognito",
        "native_profile_dir": "",
        "host_profiles_enabled": False,
        "host_learning_enabled": False,
    }
    plans: List[StagePlan] = []

    if include_headless_stage:
        plans.append(
            StagePlan(
                name="baseline_chrome_headless_safety_check",
                description=(
                    "Optional headless safety check. OS-level solver actions are now "
                    "blocked in headless mode by toolkit safeguards."
                ),
                config={
                    **baseline_common,
                    "headless": True,
                    "native_fallback_policy": "off",
                    "native_browser_channels": ["chrome", "msedge", "chromium"],
                },
                allow_headed_retry=False,
                allow_native_fallback=False,
            )
        )

    plans.extend(
        [
            StagePlan(
                name="baseline_chrome_headed_only",
                description=(
                    "Toolkit baseline path in headed Chrome only (no native fallback)."
                ),
                config={
                    **baseline_common,
                    "native_fallback_policy": "off",
                    "native_browser_channels": ["chrome", "msedge", "chromium"],
                },
                allow_headed_retry=False,
                allow_native_fallback=False,
            ),
            StagePlan(
                name="toolkit_native_chrome_default",
                description=(
                    "Toolkit chrome-first route using native fallback policy=always "
                    "(Chrome then Edge then Chromium)."
                ),
                config={
                    **baseline_common,
                    "native_fallback_policy": "always",
                    "native_browser_channels": ["chrome", "msedge", "chromium"],
                    "native_browser_headless": False,
                },
                allow_headed_retry=False,
                allow_native_fallback=True,
            ),
        ]
    )
    if not skip_interactive:
        plans.append(
            StagePlan(
                name="interactive_session_chrome",
                description="MCP InteractiveSession flow with toolkit challenge solvers (Chrome channel).",
                config={},
                allow_headed_retry=None,
                allow_native_fallback=None,
                interactive=True,
            )
        )
    if not skip_standalone_reference:
        plans.append(
            StagePlan(
                name="standalone_system_chrome_reference",
                description=(
                    "Reference run using installed Chrome + CDP with a fresh temp profile "
                    "(mirrors standalone diagnostic path)."
                ),
                config={},
                allow_headed_retry=None,
                allow_native_fallback=None,
                standalone_reference=True,
            )
        )
    return plans


def determine_smoking_gun(results: List[StageResult]) -> Dict[str, Any]:
    by_name = {result.name: result for result in results}
    baseline_headless = by_name.get("baseline_chrome_headless_safety_check")
    baseline_headed = by_name.get("baseline_chrome_headed_only")
    native_default = by_name.get("toolkit_native_chrome_default")
    interactive = by_name.get("interactive_session_chrome")
    standalone_reference = by_name.get("standalone_system_chrome_reference")
    toolkit_results = [item for item in results if not is_reference_stage_result(item)]
    toolkit_progressed = any(item.progressed for item in toolkit_results)
    findings: List[str] = []
    culprit = "No single dominant culprit detected."

    if baseline_headless and baseline_headed:
        if baseline_headless.challenge_detected and baseline_headed.progressed:
            culprit = "Headless challenge path is the blocker; headed Chrome baseline is safer."
            findings.append(
                "Headless check stayed challenged while headed baseline progressed."
            )

    if baseline_headless and baseline_headed and native_default:
        if (
            baseline_headless.challenge_detected
            and baseline_headed.challenge_detected
            and native_default.progressed
        ):
            culprit = "Playwright-managed baseline path is blocked; native Chrome channel succeeds."
            findings.append(
                "Primary blocker is automation signal mismatch. Chrome native channel should be preferred."
            )

    if baseline_headed and native_default:
        if baseline_headed.challenge_detected and native_default.progressed:
            culprit = "Headed Chrome baseline blocked; native Chrome fallback is the winning route."
            findings.append(
                "Use native_fallback_policy='always' (or 'on_blocked') with Chrome-first channels for this host."
            )

    if native_default and interactive:
        if native_default.challenge_detected and interactive.progressed:
            culprit = "Challenge requires interactive solver actions after navigation."
            findings.append(
                "Native fallback alone was insufficient; interactive solver resolved remaining challenge markers."
            )

    if native_default and native_default.error:
        low_error = native_default.error.lower()
        if "channel" in low_error or "executable" in low_error:
            culprit = (
                "Chrome channel launch issue (browser not installed or inaccessible)."
            )
            findings.append(
                "Install/repair local Chrome and verify Playwright channel launch access."
            )

    if (
        standalone_reference
        and standalone_reference.progressed
        and not toolkit_progressed
    ):
        culprit = (
            "Installed Chrome/CDP reference succeeded, but the toolkit integration "
            "path did not reproduce that runtime."
        )
        findings.append(
            "The standalone installed-browser reference confirms the host can progress with a fresh native Chrome profile."
        )
        findings.append(
            "Toolkit-native stages should be aligned against the same Chrome-first, incognito, system-browser runtime assumptions."
        )

    if not findings:
        all_blocked = all(not item.progressed for item in toolkit_results or results)
        if all_blocked:
            culprit = "All toolkit stages remained blocked."
            findings.append(
                "Likely unresolved PX/CF challenge or environment constraints (display/pyautogui)."
            )
        else:
            findings.append("Toolkit progression succeeded in at least one stage.")

    recommendations: List[str] = []
    if native_default and native_default.progressed:
        recommendations.append(
            "Set native_fallback_policy='always' or keep 'on_blocked' with native_browser_channels=['chrome','msedge','chromium']."
        )
    if baseline_headless:
        recommendations.append(
            "Keep headless disabled for PX OS-interaction workflows unless running explicit safety checks."
        )
    if interactive and not PerimeterXSolver.is_available():
        recommendations.append(
            "Install desktop extras: pip install web-scraper-toolkit[desktop]."
        )
    if (
        standalone_reference
        and standalone_reference.progressed
        and not toolkit_progressed
    ):
        recommendations.append(
            "Keep the installed-Chrome/CDP reference stage enabled while validating toolkit-native Chrome integration."
        )

    return {
        "culprit": culprit,
        "findings": findings,
        "recommendations": recommendations,
    }


async def run_suite(
    *,
    url: str,
    timeout_ms: int,
    skip_interactive: bool,
    include_headless_stage: bool,
    skip_standalone_reference: bool,
    auto_commit_host_profile: bool,
    host_profiles_path: str,
    read_only: bool,
    require_2xx_status: bool,
    save_artifacts: bool,
    artifacts_dir: str,
    fixture_record_path: str,
    fixture_replay_path: str,
) -> Dict[str, Any]:
    run_id = (
        datetime.now(timezone.utc).strftime("diag_%Y%m%dT%H%M%S_")
        + uuid.uuid4().hex[:8]
    )
    artifacts_root = Path(artifacts_dir).resolve()
    if fixture_replay_path:
        fixture_stage = build_fixture_stage_result(fixture_path=fixture_replay_path)
        log(
            "+" if fixture_stage.progressed else "-",
            (
                f"{fixture_stage.name}: progressed={fixture_stage.progressed} "
                f"status={fixture_stage.status} block_reason={fixture_stage.block_reason} "
                f"url={fixture_stage.final_url}"
            ),
        )
        log(
            "*",
            (
                f"{fixture_stage.name} evidence: likely_real_page="
                f"{fixture_stage.success_evidence.get('likely_real_page')} "
                f"marker_soft_signal_only="
                f"{fixture_stage.success_evidence.get('marker_soft_signal_only')} "
                f"words={fixture_stage.success_evidence.get('word_count_estimate')} "
                f"structure={fixture_stage.success_evidence.get('structure_signal_count')} "
                f"len={fixture_stage.content_length}"
            ),
        )
        analysis = determine_smoking_gun([fixture_stage])
        return {
            "run_id": run_id,
            "generated_utc": utc_now_iso(),
            "url": fixture_stage.final_url,
            "stages": [asdict(fixture_stage)],
            "summary": {
                "total_stages": 1,
                "progressed_stages": 1 if fixture_stage.progressed else 0,
                "blocked_stages": 0 if fixture_stage.progressed else 1,
                "toolkit_progressed_stages": 1 if fixture_stage.progressed else 0,
                "reference_progressed_stages": 0,
                "require_2xx_status": require_2xx_status,
                "artifacts_saved": False,
                "fixture_replay": True,
            },
            "analysis": analysis,
            "autocommit": {
                "autocommit_attempted": False,
                "autocommit_verified": False,
                "autocommit_written": False,
                "autocommit_reason": "fixture_replay_mode",
            },
            "artifacts": [],
        }

    plans = build_stage_plans(
        skip_interactive=skip_interactive,
        include_headless_stage=include_headless_stage,
        skip_standalone_reference=skip_standalone_reference,
    )
    stage_results: List[StageResult] = []
    artifact_manifest: List[Dict[str, str]] = []
    for plan in plans:
        log("*", f"Running stage: {plan.name}")
        stage_index = len(stage_results) + 1
        if plan.interactive:
            result = await run_interactive_stage(
                stage_index=stage_index,
                plan=plan,
                url=url,
                require_2xx_status=require_2xx_status,
            )
        elif plan.standalone_reference:
            result = await run_standalone_reference_stage(
                stage_index=stage_index,
                plan=plan,
                url=url,
                timeout_ms=timeout_ms,
                require_2xx_status=require_2xx_status,
            )
        else:
            result = await run_playwright_stage(
                stage_index=stage_index,
                plan=plan,
                url=url,
                timeout_ms=timeout_ms,
                require_2xx_status=require_2xx_status,
            )

        result.metadata.setdefault("run_id", run_id)
        result.metadata.setdefault("stage_index", stage_index)
        result.metadata.setdefault(
            "stage_id",
            f"{run_id}:{stage_index}:{slugify_name(plan.name)}",
        )

        stage_results.append(result)
        log(
            "+" if result.progressed else "-",
            (
                f"{plan.name}: progressed={result.progressed} status={result.status} "
                f"block_reason={result.block_reason} url={result.final_url}"
            ),
        )
        evidence = result.success_evidence
        log(
            "*",
            (
                f"{plan.name} evidence: likely_real_page={evidence.get('likely_real_page')} "
                f"marker_soft_signal_only={evidence.get('marker_soft_signal_only')} "
                f"words={evidence.get('word_count_estimate')} "
                f"structure={evidence.get('structure_signal_count')} "
                f"len={result.content_length}"
            ),
        )
        if result.error:
            log("!", f"{plan.name} error: {result.error}")
        if save_artifacts:
            manifest = write_stage_artifacts(
                artifacts_root=artifacts_root,
                run_id=run_id,
                stage_result=result,
            )
            artifact_manifest.append(manifest)

    analysis = determine_smoking_gun(stage_results)
    autocommit = await _autocommit_host_profile(
        url=url,
        timeout_ms=timeout_ms,
        stage_results=stage_results,
        enabled=auto_commit_host_profile,
        host_profiles_path=host_profiles_path,
        read_only=read_only,
        require_2xx_status=require_2xx_status,
    )
    progressed_count = sum(1 for item in stage_results if item.progressed)
    blocked_count = len(stage_results) - progressed_count
    toolkit_progressed_count = sum(
        1
        for item in stage_results
        if item.progressed and not is_reference_stage_result(item)
    )
    reference_progressed_count = sum(
        1
        for item in stage_results
        if item.progressed and is_reference_stage_result(item)
    )
    fixture_manifest: Dict[str, Any] = {}
    if fixture_record_path:
        record_target = next((item for item in stage_results if item.progressed), None)
        if record_target is None and stage_results:
            record_target = stage_results[-1]
        if record_target is not None:
            saved_fixture = record_sanitized_fixture(
                path=fixture_record_path,
                fixture_name=f"{slugify_name(record_target.name)}_{run_id}",
                tool_source="diag_toolkit_zoominfo.py",
                status=record_target.status,
                url=record_target.final_url,
                title=record_target.title,
                html=record_target.content_excerpt,
                headers={},
                cookies=[],
                events=[],
                expected_evidence=record_target.success_evidence,
            )
            fixture_manifest = {
                "fixture_recorded": True,
                "fixture_record_path": str(saved_fixture.resolve()),
                "fixture_record_source_stage": record_target.name,
                "fixture_record_truncated_html": True,
            }
    return {
        "run_id": run_id,
        "generated_utc": utc_now_iso(),
        "url": url,
        "stages": [asdict(item) for item in stage_results],
        "summary": {
            "total_stages": len(stage_results),
            "progressed_stages": progressed_count,
            "blocked_stages": blocked_count,
            "toolkit_progressed_stages": toolkit_progressed_count,
            "reference_progressed_stages": reference_progressed_count,
            "require_2xx_status": require_2xx_status,
            "artifacts_saved": bool(save_artifacts),
            "fixture_replay": False,
        },
        "analysis": analysis,
        "autocommit": autocommit,
        "artifacts": artifact_manifest,
        "fixture": fixture_manifest,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run toolkit-native challenge diagnostics."
    )
    parser.add_argument("--url", default=TEST_URL, help="Target URL.")
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=45000,
        help="Navigation timeout in milliseconds.",
    )
    parser.add_argument(
        "--skip-interactive",
        action="store_true",
        help="Skip the InteractiveSession stage.",
    )
    parser.add_argument(
        "--skip-standalone-reference",
        action="store_true",
        help=(
            "Skip the standalone installed-Chrome/CDP reference stage that validates "
            "the native system-browser runtime."
        ),
    )
    parser.add_argument(
        "--include-headless-stage",
        action="store_true",
        help=(
            "Include optional headless baseline stage for diagnostics. "
            "OS-level solver actions are blocked in headless mode for safety."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Python logging level for toolkit internals.",
    )
    parser.add_argument(
        "--auto-commit-host-profile",
        action="store_true",
        help=(
            "After a successful diagnostic stage, run a clean incognito verification "
            "and write host profile evidence."
        ),
    )
    parser.add_argument(
        "--host-profiles-path",
        default="./host_profiles.json",
        help="Host profile store path used by auto-commit mode.",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Read-only diagnostics mode (never write host profile updates).",
    )
    parser.add_argument(
        "--require-2xx",
        action="store_true",
        help=(
            "Require final HTTP status to be 2xx for a stage to count as progressed. "
            "Useful for strict success assertions."
        ),
    )
    parser.add_argument(
        "--save-artifacts",
        action="store_true",
        help=(
            "Write per-stage artifact bundles (JSON + content excerpt) to artifacts directory."
        ),
    )
    parser.add_argument(
        "--artifacts-dir",
        default="./scripts/out/artifacts",
        help="Directory root used when --save-artifacts is enabled.",
    )
    parser.add_argument(
        "--fixture-record",
        default="",
        help="Optional sanitized fixture output path for recording one representative stage.",
    )
    parser.add_argument(
        "--fixture-replay",
        default="",
        help="Replay a sanitized fixture instead of launching live browser stages.",
    )
    return parser


def main() -> None:
    global LOG_FILE_HANDLE

    args = build_arg_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    script_dir = Path(__file__).resolve().parent
    log_path = script_dir / "diag_zi_result.log"
    out_path = (
        script_dir
        / "out"
        / (f"diag_toolkit_zoominfo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    )
    ensure_parent(log_path)
    ensure_parent(out_path)

    LOG_FILE_HANDLE = log_path.open("w", encoding="utf-8")
    removed = scrub_pycache(script_dir.parent)
    log("*", f"Scrubbed __pycache__ folders: {removed}")
    log("*", f"Testing URL: {args.url}")
    log(
        "*",
        "Default diagnostics run headed Chrome flows first (no headless OS interaction).",
    )
    log("*", "Toolkit route preference includes chrome-first native fallback.")
    if args.skip_standalone_reference:
        log("*", "Standalone installed-Chrome/CDP reference stage is disabled.")
    else:
        log("*", "Standalone installed-Chrome/CDP reference stage is enabled.")
    if args.read_only:
        log("*", "Read-only mode enabled: host profile updates are disabled.")
    if args.require_2xx:
        log("*", "Strict progression mode enabled: only 2xx statuses count as success.")
    if args.save_artifacts:
        log("*", f"Artifact capture enabled at: {Path(args.artifacts_dir).resolve()}")
    if args.fixture_replay:
        log("*", f"Fixture replay mode: {Path(args.fixture_replay).resolve()}")
    if args.fixture_record:
        log("*", f"Fixture recording enabled at: {Path(args.fixture_record).resolve()}")

    report: Dict[str, Any] = {}
    exit_code = 1
    try:
        report = asyncio.run(
            run_suite(
                url=args.url,
                timeout_ms=max(5000, int(args.timeout_ms)),
                skip_interactive=bool(args.skip_interactive),
                include_headless_stage=bool(args.include_headless_stage),
                skip_standalone_reference=bool(args.skip_standalone_reference),
                auto_commit_host_profile=bool(args.auto_commit_host_profile),
                host_profiles_path=str(args.host_profiles_path),
                read_only=bool(args.read_only),
                require_2xx_status=bool(args.require_2xx),
                save_artifacts=bool(args.save_artifacts),
                artifacts_dir=str(args.artifacts_dir),
                fixture_record_path=str(args.fixture_record or ""),
                fixture_replay_path=str(args.fixture_replay or ""),
            )
        )
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        analysis = report.get("analysis", {})
        log("*", f"Likely culprit: {analysis.get('culprit', 'n/a')}")
        for finding in analysis.get("findings", []):
            log("*", f"Finding: {finding}")
        for recommendation in analysis.get("recommendations", []):
            log("*", f"Recommendation: {recommendation}")
        autocommit = report.get("autocommit", {})
        if autocommit.get("autocommit_attempted"):
            log(
                "*",
                (
                    "Auto-commit: verified="
                    f"{autocommit.get('autocommit_verified')} "
                    f"written={autocommit.get('autocommit_written')} "
                    f"reason={autocommit.get('autocommit_reason')}"
                ),
            )
            if autocommit.get("autocommit_target_host_key"):
                log(
                    "*",
                    "Auto-commit target host key: "
                    f"{autocommit.get('autocommit_target_host_key')}",
                )
        log("*", f"JSON report saved: {out_path}")

        progressed = int(
            report.get("summary", {}).get(
                "toolkit_progressed_stages",
                report.get("summary", {}).get("progressed_stages", 0),
            )
        )
        exit_code = 0 if progressed > 0 else 1
    except Exception as exc:
        log("-", f"Fatal error: {exc}")
        exit_code = 1
    finally:
        if LOG_FILE_HANDLE is not None:
            LOG_FILE_HANDLE.flush()
            LOG_FILE_HANDLE.close()
            LOG_FILE_HANDLE = None
        log("+" if exit_code == 0 else "-", f"Exit code: {exit_code}")
        sys.stdout.flush()
        os._exit(exit_code)


if __name__ == "__main__":
    main()
