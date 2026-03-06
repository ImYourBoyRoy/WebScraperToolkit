# ./scripts/zoominfo_diagnostic_matrix.py
"""
ZoomInfo anti-bot diagnostics harness with multi-variant testing and smoking-gun analysis.
Run: python ./scripts/zoominfo_diagnostic_matrix.py [--variants baseline,minimal_stealth] [--runs-per-variant 2]
Inputs: CLI flags (URL, variant list, run counts, hold method, timeouts), optional pyautogui for OS hold.
Outputs: JSON + Markdown summaries and screenshots under ./scripts/out/zoominfo_diagnostic_matrix/run_<timestamp>/.
Side effects: Launches headed Chrome; with --hold-method os it will move/click the real cursor.
Exit codes: 0 if any run reaches non-challenge progression, 1 if all runs remain blocked, 2 for config errors.
Operational notes: Testing-only instrumentation; does not bypass policy controls or mutate target-side behavior.
Progression classification uses deterministic content/title/structure evidence, not strict URL-only checks.
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from playwright.async_api import (
    Locator,
    Page,
    async_playwright,
)

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

try:
    import pyautogui  # type: ignore

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0
    HAS_PYAUTOGUI = True
except Exception:
    pyautogui = None
    HAS_PYAUTOGUI = False

DEFAULT_URL = "https://example.com/"
DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "out" / "zoominfo_diagnostic_matrix"
BLOCKED_STATUSES: Set[int] = {403, 429}
SEVERITY_POINTS: Dict[str, float] = {
    "critical": 25.0,
    "high": 15.0,
    "medium": 8.0,
    "low": 3.0,
}
PX_COOKIE_NAMES: Set[str] = {"_px3", "_pxde", "_pxvid", "_pxhd"}

LEGACY_STEALTH_JS = r"""
(() => {
  try { delete Object.getPrototypeOf(navigator).webdriver; } catch (e) {}
  try { Object.defineProperty(navigator, "languages", { get: () => Object.freeze(["en-US", "en"]) }); } catch (e) {}
  try { Object.defineProperty(navigator, "hardwareConcurrency", { get: () => 4 }); } catch (e) {}
  try { Object.defineProperty(navigator, "deviceMemory", { get: () => 8 }); } catch (e) {}
  try { Object.defineProperty(navigator, "maxTouchPoints", { get: () => 0 }); } catch (e) {}
  try { if (!window.chrome) window.chrome = {}; if (!window.chrome.runtime) window.chrome.runtime = { connect: () => {}, sendMessage: () => {} }; } catch (e) {}
  try {
    const q = navigator.permissions.query.bind(navigator.permissions);
    Object.defineProperty(navigator.permissions, "query", { value: (d) => d && d.name === "notifications" ? Promise.resolve({ state: Notification.permission || "default" }) : q(d) });
  } catch (e) {}
  try { Object.defineProperty(Notification, "permission", { get: () => "default" }); } catch (e) {}
})();
"""

MINIMAL_STEALTH_JS = r"""
(() => {
  try { delete Object.getPrototypeOf(navigator).webdriver; } catch (e) {}
  try { Object.defineProperty(navigator, "languages", { get: () => Object.freeze(["en-US", "en"]) }); } catch (e) {}
})();
"""

# Full stealth JS matching diag_zoominfo_bypass.py's init script.
# Uses generic safe defaults for hardware values since the diagnostic
# harness doesn't do a per-run hardware probe.
BYPASS_STEALTH_JS = r"""
(() => {
  try { delete Object.getPrototypeOf(navigator).webdriver; } catch (e) {}
  Object.defineProperty(navigator, 'languages', {
    get: () => Object.freeze(["en-US", "en"]),
    configurable: false, enumerable: true
  });
  Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => 4, configurable: false, enumerable: true
  });
  Object.defineProperty(navigator, 'deviceMemory', {
    get: () => 8, configurable: false, enumerable: true
  });
  if (!window.chrome) window.chrome = {};
  if (!window.chrome.runtime) {
    window.chrome.runtime = { connect: () => {}, sendMessage: () => {} };
  }
  const origQuery = navigator.permissions.query.bind(navigator.permissions);
  Object.defineProperty(navigator.permissions, 'query', {
    value: (desc) => {
      if (desc && desc.name === 'notifications') {
        return Promise.resolve({ state: Notification.permission || 'default' });
      }
      return origQuery(desc);
    },
    configurable: false, enumerable: true
  });
  try {
    Object.defineProperty(Notification, 'permission', {
      get: () => 'default', configurable: false, enumerable: true
    });
  } catch(e) {}
  try {
    if (navigator.plugins.length === 0) {
      const fakePlugins = [
        { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 2 },
        { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 2 },
        { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 2 },
        { name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 2 },
        { name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 2 },
      ];
      Object.defineProperty(navigator, 'plugins', {
        get: () => fakePlugins, configurable: false, enumerable: true
      });
        }
  } catch(e) {}
  try {
    if (navigator.connection) {
      Object.defineProperty(navigator.connection, 'rtt', {
        get: () => 50, configurable: false, enumerable: true
      });
        }
  } catch(e) {}
})();
"""

TRACKER_DOMAINS: List[str] = [
    "google-analytics.com",
    "googletagmanager.com",
    "doubleclick.net",
    "scorecardresearch.com",
    "adservice.google.com",
    "connect.facebook.net",
    "criteo.com",
    "hotjar.com",
    "optimizely.com",
]

PX_CONTENT_MARKERS: Tuple[str, ...] = (
    "px-captcha",
    "press & hold",
    "press &amp; hold",
    "perimeterx",
    "human challenge",
)
CF_CONTENT_MARKERS: Tuple[str, ...] = (
    "performing security verification",
    "cloudflare",
    "__cf_chl",
    "just a moment",
    "attention required",
)
TITLE_CHALLENGE_MARKERS: Tuple[str, ...] = (
    "just a moment",
    "attention required",
    "access to this page has been denied",
    "access denied",
    "verify you are human",
)


@dataclass
class VariantConfig:
    name: str
    description: str
    launch_args: List[str] = field(default_factory=list)
    ignore_default_automation: bool = False
    init_script: Optional[str] = None
    has_touch: Optional[bool] = None
    use_persistent_profile: bool = False


@dataclass
class HoldAttempt:
    attempted: bool
    method: str
    hold_seconds: float
    locator_strategy: Optional[str]
    box: Optional[Dict[str, float]]
    completed_marker_seen: bool
    error: Optional[str] = None


@dataclass
class SmokingGunSignal:
    signal_id: str
    severity: str
    confidence: float
    finding: str
    evidence: Dict[str, Any]


@dataclass
class VariantDiagnosis:
    score: float
    verdict: str
    signals: List[SmokingGunSignal]


@dataclass
class VariantRunResult:
    variant: str
    run_index: int
    started_utc: str
    config: Dict[str, Any]
    initial_nav: Dict[str, Any]
    initial_state: Dict[str, Any]
    fingerprint_before: Dict[str, Any]
    hold: HoldAttempt
    post_hold_state: Dict[str, Any]
    post_hold_fetch_status: Optional[int]
    revisit_nav: Dict[str, Any]
    observe_titles: List[str]
    final_state: Dict[str, Any]
    fingerprint_after: Dict[str, Any]
    cookies_initial: List[Dict[str, Any]]
    cookies_post_hold: List[Dict[str, Any]]
    cookies_final: List[Dict[str, Any]]
    event_log: List[Dict[str, Any]]
    screenshot_path: str
    diagnosis: VariantDiagnosis


@dataclass
class SuiteSummary:
    generated_utc: str
    url: str
    total_runs: int
    successful_runs: int
    blocked_runs: int
    variant_matrix: List[Dict[str, Any]]
    recurring_signals: List[Dict[str, Any]]
    strongest_conclusion: str


def log(message: str) -> None:
    print(message, flush=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def scrub_pycache(root: Path) -> int:
    removed = 0
    for folder in root.rglob("__pycache__"):
        shutil.rmtree(folder, ignore_errors=True)
        removed += 1
    return removed


def normalize_headers(raw: Dict[str, str]) -> Dict[str, str]:
    return {str(k).lower(): str(v) for k, v in raw.items()}


def parse_cookie_names_from_header(cookie_header: str) -> List[str]:
    if not cookie_header:
        return []
    names: List[str] = []
    for part in cookie_header.split(";"):
        item = part.strip()
        if not item or "=" not in item:
            continue
        names.append(item.split("=", 1)[0].strip())
    return [n for n in names if n]


def count_marker_hits(content: str, markers: Tuple[str, ...]) -> int:
    lowered = content.lower()
    return sum(lowered.count(marker) for marker in markers)


def estimate_text_word_count(content: str) -> int:
    text = re.sub(r"<[^>]+>", " ", content)
    return len(re.findall(r"[a-zA-Z]{3,}", text))


def count_structure_signals(content: str) -> int:
    lowered = content.lower()
    signals = (
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
    )
    return sum(1 for signal in signals if signal in lowered)


def focused_cookies(cookies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    focused: List[Dict[str, Any]] = []
    for cookie in cookies:
        name = str(cookie.get("name", ""))
        if name.startswith("_px") or name.startswith("cf"):
            focused.append(
                {
                    "name": name,
                    "domain": cookie.get("domain"),
                    "path": cookie.get("path"),
                    "secure": cookie.get("secure"),
                    "sameSite": cookie.get("sameSite"),
                    "expires": cookie.get("expires"),
                    "value_length": len(str(cookie.get("value", ""))),
                }
            )
    return focused


def cookie_name_set(cookies: List[Dict[str, Any]]) -> Set[str]:
    return {str(c.get("name", "")) for c in cookies}


def categorize_url(url: str, target_url: str) -> str:
    u = url.lower()
    t = target_url.lower()
    if u.startswith(t):
        return "main_doc"
    target_host = (urlparse(target_url).hostname or "").lower()
    current_host = (urlparse(url).hostname or "").lower()
    if target_host and current_host == target_host:
        return "target_host"
    if any(
        k in u
        for k in ("px-cloud", "perimeterx", "/captcha/", "/osx7m0dx/", "px-client")
    ):
        return "perimeterx"
    if any(k in u for k in ("__cf_chl", "cloudflare", "cf-chl")):
        return "cloudflare"
    return "other"


def default_variants() -> Dict[str, VariantConfig]:
    base_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]
    return {
        "baseline": VariantConfig(
            "baseline",
            "No JS stealth patches (control group).",
            list(base_args),
            False,
            None,
            None,
            False,
        ),
        "minimal_stealth": VariantConfig(
            "minimal_stealth",
            "Only webdriver + languages patching.",
            list(base_args),
            True,
            MINIMAL_STEALTH_JS,
            None,
            False,
        ),
        "legacy_stealth": VariantConfig(
            "legacy_stealth",
            "Legacy-style broader patch set from prior attempts.",
            list(base_args),
            True,
            LEGACY_STEALTH_JS,
            False,
            False,
        ),
        "persistent_minimal": VariantConfig(
            "persistent_minimal",
            "Persistent profile + minimal stealth.",
            list(base_args),
            True,
            MINIMAL_STEALTH_JS,
            None,
            True,
        ),
        "persistent_legacy": VariantConfig(
            "persistent_legacy",
            "Persistent profile + legacy stealth.",
            list(base_args),
            True,
            LEGACY_STEALTH_JS,
            False,
            True,
        ),
        "bypass_match": VariantConfig(
            "bypass_match",
            "Full config matching diag_zoominfo_bypass.py (stealth+accept-lang+UA+tracker-block).",
            list(base_args),
            True,
            BYPASS_STEALTH_JS,
            False,
            False,
        ),
    }


async def safe_title(page: Page) -> str:
    try:
        return await page.title()
    except Exception:
        return "<title-unavailable>"


async def safe_content(page: Page) -> str:
    try:
        return await page.content()
    except Exception:
        return ""


async def collect_fingerprint(page: Page) -> Dict[str, Any]:
    return await page.evaluate(
        """() => {
            const out = {};
            out.ua = navigator.userAgent;
            out.webdriver = navigator.webdriver;
            out.languages = navigator.languages ? Array.from(navigator.languages) : [];
            out.language = navigator.language || null;
            out.platform = navigator.platform || null;
            out.vendor = navigator.vendor || null;
            out.maxTouchPoints = navigator.maxTouchPoints;
            out.hardwareConcurrency = navigator.hardwareConcurrency;
            out.deviceMemory = navigator.deviceMemory;
            out.notificationPermission = Notification.permission;

            const permissionsQuery = navigator.permissions?.query?.toString?.() || null;
            out.permissionsQueryToString = permissionsQuery;
            out.permissionsQueryLooksNative = permissionsQuery ? /\\[native code\\]/.test(permissionsQuery) : null;

            out.playwrightMarkers = [];
            if ("__playwright__binding__" in window) out.playwrightMarkers.push("__playwright__binding__");
            if ("__pwInitScripts" in window) out.playwrightMarkers.push("__pwInitScripts");
            out.cdcMarkers = Object.keys(window).filter(k => k.startsWith("cdc_")).slice(0, 5);

            out.webgl = null;
            try {
              const canvas = document.createElement("canvas");
              const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
              if (gl) {
                const dbg = gl.getExtension("WEBGL_debug_renderer_info");
                out.webgl = {
                  vendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
                  renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)
                };
              }
            } catch (e) {
              out.webgl = { error: String(e) };
            }

            out.uaData = null;
            try {
              if (navigator.userAgentData) {
                out.uaData = {
                  brands: navigator.userAgentData.brands || null,
                  mobile: navigator.userAgentData.mobile || null,
                  platform: navigator.userAgentData.platform || null
                };
              }
            } catch (e) {
              out.uaData = { error: String(e) };
            }

            return out;
        }"""
    )


async def detect_challenge_state(page: Page) -> Dict[str, Any]:
    title = await safe_title(page)
    raw_content = await safe_content(page)
    content = raw_content.lower()

    press_hold_visible = False
    completed_visible = False
    press_hold_count = 0
    completed_count = 0

    for frame in page.frames:
        try:
            press_btn = frame.get_by_role("button", name="Press & Hold")
            count = await press_btn.count()
            press_hold_count += count
            if count > 0 and await press_btn.first.is_visible():
                press_hold_visible = True
        except Exception:
            pass

        try:
            done_btn = frame.get_by_role("button", name="Human Challenge completed")
            count = await done_btn.count()
            completed_count += count
            if count > 0:
                completed_visible = True
        except Exception:
            pass

    lower_title = title.lower()
    title_challenge = any(marker in lower_title for marker in TITLE_CHALLENGE_MARKERS)
    has_cf_chl_param = "__cf_chl" in page.url.lower()

    px_marker_hits = count_marker_hits(content, PX_CONTENT_MARKERS)
    cf_marker_hits = count_marker_hits(content, CF_CONTENT_MARKERS)
    marker_hits_total = px_marker_hits + cf_marker_hits
    marker_density = marker_hits_total / max(1, len(raw_content))

    word_count_estimate = estimate_text_word_count(raw_content)
    structure_signal_count = count_structure_signals(raw_content)
    rich_content_length = len(raw_content) >= 120_000
    likely_real_page = bool(
        raw_content.strip()
        and not title_challenge
        and (
            rich_content_length
            or word_count_estimate >= 450
            or structure_signal_count >= 6
        )
    )
    marker_soft_signal_only = bool(
        likely_real_page
        and marker_hits_total > 0
        and marker_density < 0.00025
        and not has_cf_chl_param
    )
    effective_challenge_detected = bool(
        title_challenge
        or (has_cf_chl_param and not marker_soft_signal_only and not likely_real_page)
        or (press_hold_visible and not marker_soft_signal_only)
        or (
            marker_hits_total > 0
            and not marker_soft_signal_only
            and marker_density >= 0.00025
            and not likely_real_page
        )
    )

    return {
        "title": title,
        "url": page.url,
        "frame_count": len(page.frames),
        "access_denied_title": "access to this page has been denied" in lower_title,
        "just_a_moment_title": "just a moment" in lower_title,
        "title_challenge": title_challenge,
        "has_cf_chl_param": has_cf_chl_param,
        "press_hold_visible": press_hold_visible,
        "press_hold_count": press_hold_count,
        "completed_marker_visible": completed_visible,
        "completed_marker_count": completed_count,
        "content_has_px_markers": px_marker_hits > 0,
        "content_has_cf_markers": cf_marker_hits > 0,
        "content_length": len(raw_content),
        "word_count_estimate": word_count_estimate,
        "structure_signal_count": structure_signal_count,
        "rich_content_length": rich_content_length,
        "marker_hits_total": marker_hits_total,
        "marker_density": marker_density,
        "likely_real_page": likely_real_page,
        "marker_soft_signal_only": marker_soft_signal_only,
        "effective_challenge_detected": effective_challenge_detected,
    }


async def find_press_hold_locator(
    page: Page,
) -> Tuple[Optional[Locator], Optional[Dict[str, float]], Optional[str]]:
    candidates: List[Tuple[Locator, Dict[str, float], str]] = []
    for frame in page.frames:
        try:
            by_role = frame.get_by_role("button", name="Press & Hold")
            if await by_role.count() > 0 and await by_role.first.is_visible():
                box = await by_role.first.bounding_box()
                if box:
                    candidates.append((by_role, box, "aria_button"))
        except Exception:
            pass

        try:
            inner = frame.locator("#px-captcha button")
            if await inner.count() > 0 and await inner.first.is_visible():
                box = await inner.first.bounding_box()
                if box:
                    candidates.append((inner, box, "container_button"))
        except Exception:
            pass

        try:
            container = frame.locator("#px-captcha")
            if await container.count() > 0 and await container.first.is_visible():
                box = await container.first.bounding_box()
                if box:
                    candidates.append((container, box, "container"))
        except Exception:
            pass

    if not candidates:
        return None, None, None

    candidates.sort(key=lambda item: item[1]["width"] * item[1]["height"])
    best_locator, best_box, best_strategy = candidates[0]
    return best_locator, best_box, best_strategy


async def completion_marker_seen(page: Page) -> bool:
    state = await detect_challenge_state(page)
    return bool(state["completed_marker_visible"])


async def _window_metrics(page: Page) -> Dict[str, float]:
    return await page.evaluate(
        """() => ({
            screenX: window.screenX,
            screenY: window.screenY,
            outerH: window.outerHeight,
            innerH: window.innerHeight,
            chromeH: window.outerHeight - window.innerHeight,
            dpr: window.devicePixelRatio || 1
        })"""
    )


def _viewport_to_screen(
    win_info: Dict[str, float], vp_x: float, vp_y: float
) -> Tuple[float, float]:
    dpr = float(win_info.get("dpr", 1.0))
    return (
        (float(win_info["screenX"]) + vp_x) * dpr,
        (float(win_info["screenY"]) + float(win_info["chromeH"]) + vp_y) * dpr,
    )


def _os_mouse_move(target_x: float, target_y: float, duration: float) -> None:
    if pyautogui is None:
        return
    start_x, start_y = pyautogui.position()
    cp_x = (
        start_x
        + (target_x - start_x) * random.uniform(0.3, 0.7)
        + random.uniform(-80, 80)
    )
    cp_y = (
        start_y
        + (target_y - start_y) * random.uniform(0.3, 0.7)
        + random.uniform(-80, 80)
    )
    steps = random.randint(18, 32)
    for i in range(1, steps + 1):
        t = i / steps
        t_eased = 1 - pow(1 - t, 3)
        ix = (
            (1 - t_eased) ** 2 * start_x
            + 2 * (1 - t_eased) * t_eased * cp_x
            + t_eased**2 * target_x
        )
        iy = (
            (1 - t_eased) ** 2 * start_y
            + 2 * (1 - t_eased) * t_eased * cp_y
            + t_eased**2 * target_y
        )
        pyautogui.moveTo(ix, iy, duration=duration / steps, _pause=False)
    pyautogui.moveTo(target_x, target_y, duration=0.08, _pause=False)


async def attempt_playwright_hold(page: Page, hold_seconds: float) -> HoldAttempt:
    locator, box, strategy = await find_press_hold_locator(page)
    if locator is None or box is None:
        return HoldAttempt(
            False,
            "playwright",
            hold_seconds,
            None,
            None,
            False,
            "Press & Hold locator not found.",
        )

    try:
        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2
        await page.mouse.move(x, y, steps=24)
        await page.mouse.down()
        seen = False
        started = time.monotonic()
        while time.monotonic() - started < hold_seconds:
            await asyncio.sleep(0.25)
            if await completion_marker_seen(page):
                seen = True
                break
        await page.mouse.up()
        await asyncio.sleep(0.9)
        return HoldAttempt(True, "playwright", hold_seconds, strategy, box, seen, None)
    except Exception as exc:
        try:
            await page.mouse.up()
        except Exception:
            pass
        return HoldAttempt(
            True,
            "playwright",
            hold_seconds,
            strategy,
            box,
            False,
            f"{type(exc).__name__}: {exc}",
        )


async def attempt_os_hold(page: Page, hold_seconds: float) -> HoldAttempt:
    if not HAS_PYAUTOGUI:
        return HoldAttempt(
            False, "os", hold_seconds, None, None, False, "pyautogui unavailable."
        )

    locator, box, strategy = await find_press_hold_locator(page)
    if locator is None or box is None:
        return HoldAttempt(
            False,
            "os",
            hold_seconds,
            None,
            None,
            False,
            "Press & Hold locator not found.",
        )

    try:
        await page.bring_to_front()
        await asyncio.sleep(0.3)
        win = await _window_metrics(page)
        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2
        sx, sy = _viewport_to_screen(win, x, y)
        _os_mouse_move(sx, sy, duration=0.65)
        await asyncio.sleep(0.1)
        pyautogui.mouseDown()
        seen = False
        started = time.monotonic()
        while time.monotonic() - started < hold_seconds:
            await asyncio.sleep(0.25)
            if await completion_marker_seen(page):
                seen = True
                break
        pyautogui.mouseUp()
        await asyncio.sleep(0.9)
        return HoldAttempt(True, "os", hold_seconds, strategy, box, seen, None)
    except Exception as exc:
        try:
            pyautogui.mouseUp()
        except Exception:
            pass
        return HoldAttempt(
            True,
            "os",
            hold_seconds,
            strategy,
            box,
            False,
            f"{type(exc).__name__}: {exc}",
        )


async def wait_for_challenge_or_terminal(
    page: Page, wait_seconds: int
) -> Dict[str, Any]:
    state = await detect_challenge_state(page)
    if (
        state["press_hold_visible"]
        or state["access_denied_title"]
        or state["just_a_moment_title"]
    ):
        return state
    for _ in range(max(1, wait_seconds)):
        await asyncio.sleep(1.0)
        state = await detect_challenge_state(page)
        if (
            state["press_hold_visible"]
            or state["access_denied_title"]
            or state["just_a_moment_title"]
        ):
            break
    return state


_BROWSER_PATHS = {
    "chrome": [
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
    ],
    "edge": [
        os.path.expandvars(
            r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
        ),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
    ],
}


def _find_browser(browser: str = "chrome") -> str:
    candidates = _BROWSER_PATHS.get(browser, [])
    for path in candidates:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError(f"{browser.title()} not found.")


async def capture_main_nav(
    page: Page, url: str, timeout_ms: int, stage: str
) -> Dict[str, Any]:
    status: Optional[int] = None
    nav_error: Optional[str] = None
    request_headers: Dict[str, str] = {}
    response_headers: Dict[str, str] = {}

    try:
        response = await page.goto(
            url, wait_until="domcontentloaded", timeout=timeout_ms
        )
        if response is not None:
            status = response.status
            try:
                request_headers = normalize_headers(
                    await response.request.all_headers()
                )
            except Exception:
                request_headers = {}
            try:
                response_headers = normalize_headers(await response.all_headers())
            except Exception:
                response_headers = {}
    except Exception as exc:
        nav_error = f"{type(exc).__name__}: {exc}"

    cookie_names = parse_cookie_names_from_header(request_headers.get("cookie", ""))
    return {
        "stage": stage,
        "status": status,
        "url": page.url,
        "title": await safe_title(page),
        "error": nav_error,
        "request_headers": request_headers,
        "response_headers": response_headers,
        "request_cookie_names": cookie_names,
        "response_server": response_headers.get("server"),
        "response_cf_ray": response_headers.get("cf-ray"),
    }


async def fetch_status_with_credentials(page: Page, url: str) -> Optional[int]:
    try:
        status = await page.evaluate(
            """async (targetUrl) => {
                try {
                    const r = await fetch(targetUrl, { credentials: "include" });
                    return r.status;
                } catch (e) {
                    return null;
                }
            }""",
            url,
        )
        return status if isinstance(status, int) else None
    except Exception:
        return None


async def observe_titles(page: Page, seconds: int) -> List[str]:
    seen: List[str] = []
    for _ in range(max(1, seconds)):
        await asyncio.sleep(1.0)
        title = await safe_title(page)
        if not seen or seen[-1] != title:
            seen.append(title)
    return seen


def attach_event_watchers(
    page: Page, target_url: str, event_log: List[Dict[str, Any]], max_events: int
) -> Tuple[Any, Any]:
    t0 = time.monotonic()

    def _append(event: Dict[str, Any]) -> None:
        if len(event_log) < max_events:
            event_log.append(event)

    def on_request(req: Any) -> None:
        category = categorize_url(req.url, target_url)
        if category == "other":
            return
        _append(
            {
                "t_ms": int((time.monotonic() - t0) * 1000),
                "kind": "request",
                "category": category,
                "method": req.method,
                "url": req.url,
                "is_navigation": req.is_navigation_request(),
                "resource_type": req.resource_type,
            }
        )

    async def on_response(resp: Any) -> None:
        category = categorize_url(resp.url, target_url)
        if category == "other":
            return
        req = resp.request
        entry: Dict[str, Any] = {
            "t_ms": int((time.monotonic() - t0) * 1000),
            "kind": "response",
            "category": category,
            "method": req.method,
            "url": resp.url,
            "status": resp.status,
            "is_navigation": req.is_navigation_request(),
            "resource_type": req.resource_type,
        }
        # Capture PX collector response bodies — these contain scoring/clearance data
        if category == "perimeterx" and req.method == "POST" and "bundle" in resp.url:
            try:
                body = await resp.text()
                entry["response_body_preview"] = body[:1000]
            except Exception:
                entry["response_body_preview"] = "<could not read>"
            try:
                resp_headers = await resp.all_headers()
                set_cookie = resp_headers.get("set-cookie", "")
                if set_cookie:
                    entry["response_set_cookie"] = set_cookie[:500]
            except Exception:
                pass
        _append(entry)

    def _on_response_sync(resp: Any) -> None:
        asyncio.ensure_future(on_response(resp))

    page.on("request", on_request)
    page.on("response", _on_response_sync)
    return on_request, _on_response_sync


def _add_signal(
    signals: List[SmokingGunSignal],
    signal_id: str,
    severity: str,
    confidence: float,
    finding: str,
    evidence: Dict[str, Any],
) -> None:
    signals.append(
        SmokingGunSignal(
            signal_id=signal_id,
            severity=severity,
            confidence=round(max(0.0, min(1.0, confidence)), 3),
            finding=finding,
            evidence=evidence,
        )
    )


def diagnose_run(result: VariantRunResult) -> VariantDiagnosis:
    signals: List[SmokingGunSignal] = []
    fp = result.fingerprint_before
    initial = result.initial_state
    final = result.final_state
    initial_nav = result.initial_nav
    revisit_nav = result.revisit_nav

    initial_status = initial_nav.get("status")
    revisit_status = revisit_nav.get("status")

    initial_likely_real = bool(initial.get("likely_real_page", False))
    final_likely_real = bool(final.get("likely_real_page", False))
    final_marker_soft_signal = bool(final.get("marker_soft_signal_only", False))
    final_effective_challenge = bool(final.get("effective_challenge_detected", False))

    blocked_initial = bool(
        (
            initial.get("access_denied_title")
            or initial.get("just_a_moment_title")
            or initial_status in BLOCKED_STATUSES
        )
        and not initial_likely_real
    )
    blocked_revisit = bool(
        (
            final.get("access_denied_title")
            or final.get("just_a_moment_title")
            or final_effective_challenge
            or revisit_status in BLOCKED_STATUSES
        )
        and not final_likely_real
        and not final_marker_soft_signal
    )

    if blocked_initial:
        _add_signal(
            signals,
            "initial_blocked_response",
            "critical",
            0.97,
            "Initial navigation is blocked (403/429 or challenge title).",
            {"status": initial_status, "title": initial.get("title")},
        )

    if result.hold.attempted and result.hold.completed_marker_seen and blocked_revisit:
        _add_signal(
            signals,
            "ui_solved_but_backend_denied",
            "critical",
            0.99,
            "Press & Hold UI completed, but revisit stayed blocked.",
            {
                "revisit_status": revisit_status,
                "final_title": final.get("title"),
                "hold_method": result.hold.method,
            },
        )

    if (
        result.hold.attempted
        and not result.hold.completed_marker_seen
        and final.get("press_hold_visible")
    ):
        _add_signal(
            signals,
            "hold_not_accepted",
            "high",
            0.9,
            "Hold interaction did not produce completion marker and challenge remained visible.",
            {
                "final_press_hold_visible": final.get("press_hold_visible"),
                "hold_error": result.hold.error,
            },
        )

    if fp.get("webdriver") is True:
        _add_signal(
            signals,
            "webdriver_exposed",
            "critical",
            0.97,
            "navigator.webdriver is still true.",
            {"webdriver": fp.get("webdriver")},
        )

    ua = str(fp.get("ua") or "")
    if "HeadlessChrome" in ua:
        _add_signal(
            signals,
            "headless_ua_token",
            "high",
            0.95,
            "User-Agent exposes HeadlessChrome token.",
            {"ua": ua},
        )

    if result.config.get("has_touch") is False and fp.get("maxTouchPoints") not in (
        0,
        None,
    ):
        _add_signal(
            signals,
            "touch_spoof_failed",
            "high",
            0.88,
            "Variant requested has_touch=False but maxTouchPoints is non-zero.",
            {
                "configured_has_touch": result.config.get("has_touch"),
                "observed_maxTouchPoints": fp.get("maxTouchPoints"),
            },
        )

    if (
        result.config.get("init_script")
        and fp.get("permissionsQueryLooksNative") is False
    ):
        _add_signal(
            signals,
            "permissions_hook_non_native",
            "medium",
            0.74,
            "permissions.query override appears non-native (possible fingerprint tell).",
            {"permissionsQueryToString": fp.get("permissionsQueryToString")},
        )

    lang_header = str(initial_nav.get("request_headers", {}).get("accept-language", ""))
    languages = fp.get("languages") or []
    if isinstance(languages, list) and languages:
        first_lang = str(languages[0]).lower()
        if lang_header and not lang_header.lower().startswith(first_lang):
            _add_signal(
                signals,
                "accept_language_mismatch",
                "medium",
                0.7,
                "Navigator language and Accept-Language header diverge.",
                {
                    "navigator_languages": languages,
                    "accept_language_header": lang_header,
                },
            )

    if blocked_revisit and fp.get("webdriver") in (False, None):
        _add_signal(
            signals,
            "clean_client_fp_still_blocked",
            "high",
            0.83,
            "Client-side fingerprint appears mostly clean but backend still blocks progression.",
            {
                "revisit_status": revisit_status,
                "title": final.get("title"),
                "playwright_markers": fp.get("playwrightMarkers"),
            },
        )

    post_cookie_names = cookie_name_set(result.cookies_post_hold)
    final_cookie_names = cookie_name_set(result.cookies_final)
    combined_cookie_names = post_cookie_names | final_cookie_names
    has_px_clearance = any(name in combined_cookie_names for name in PX_COOKIE_NAMES)

    if result.hold.attempted and not has_px_clearance and blocked_revisit:
        _add_signal(
            signals,
            "no_px_clearance_cookies_after_hold",
            "high",
            0.86,
            "After hold attempt, no PX clearance cookies were observed.",
            {
                "cookies_post_hold": sorted(post_cookie_names),
                "cookies_final": sorted(final_cookie_names),
            },
        )

    if result.hold.attempted and has_px_clearance and blocked_revisit:
        _add_signal(
            signals,
            "px_cookies_present_but_ignored",
            "critical",
            0.96,
            "PX/CF cookies exist but target remains blocked on revisit.",
            {
                "cookies": sorted(combined_cookie_names),
                "revisit_status": revisit_status,
                "final_title": final.get("title"),
            },
        )

    revisit_cookie_names = set(revisit_nav.get("request_cookie_names") or [])
    if (
        blocked_revisit
        and has_px_clearance
        and not revisit_cookie_names.intersection(PX_COOKIE_NAMES)
    ):
        _add_signal(
            signals,
            "px_cookies_not_sent_on_revisit",
            "high",
            0.82,
            "Revisit navigation did not include PX cookie names in request header capture.",
            {
                "revisit_cookie_names": sorted(revisit_cookie_names),
                "available_cookie_names": sorted(combined_cookie_names),
            },
        )

    if (revisit_status == 429 and not final_likely_real) or final.get(
        "just_a_moment_title"
    ):
        _add_signal(
            signals,
            "cloudflare_rate_or_loop",
            "high",
            0.92,
            "Cloudflare challenge/rate-limit loop observed after interaction.",
            {
                "revisit_status": revisit_status,
                "final_title": final.get("title"),
                "final_url": final.get("url"),
            },
        )

    if initial_status == 403 and revisit_status == 429 and not final_likely_real:
        _add_signal(
            signals,
            "escalated_403_to_429",
            "medium",
            0.78,
            "Defense escalated from immediate deny to rate-limited challenge on revisit.",
            {"initial_status": initial_status, "revisit_status": revisit_status},
        )

    score = 0.0
    for signal in signals:
        score += SEVERITY_POINTS.get(signal.severity, 0.0) * signal.confidence
    score = round(min(100.0, score), 2)

    signal_ids = {s.signal_id for s in signals}
    if "ui_solved_but_backend_denied" in signal_ids:
        verdict = "Strong smoking gun: UI challenge completion is not granting backend trust/clearance."
    elif "webdriver_exposed" in signal_ids:
        verdict = "Primary client-side smoking gun: navigator.webdriver is exposed."
    elif "headless_ua_token" in signal_ids:
        verdict = "Primary client-side smoking gun: headless UA token is exposed."
    elif "cloudflare_rate_or_loop" in signal_ids:
        verdict = "Likely rate/reputation barrier: Cloudflare loop persists after challenge flow."
    elif blocked_revisit:
        verdict = "Revisit remains blocked; likely layered server-side scoring with no single client-side trigger isolated."
    else:
        verdict = (
            "No major smoking gun detected; progression appears improved for this run."
        )

    return VariantDiagnosis(score=score, verdict=verdict, signals=signals)


def is_successful_progression(result: VariantRunResult) -> bool:
    final = result.final_state
    revisit_status = result.revisit_nav.get("status")
    likely_real = bool(final.get("likely_real_page", False))
    marker_soft_signal = bool(final.get("marker_soft_signal_only", False))
    effective_challenge = bool(final.get("effective_challenge_detected", False))

    if likely_real and (marker_soft_signal or not effective_challenge):
        return True

    if revisit_status in BLOCKED_STATUSES and not likely_real:
        return False
    if final.get("access_denied_title"):
        return False
    if final.get("just_a_moment_title"):
        return False
    if final.get("press_hold_visible") and not likely_real:
        return False
    if effective_challenge and not marker_soft_signal:
        return False
    return likely_real


def build_suite_summary(url: str, results: List[VariantRunResult]) -> SuiteSummary:
    total = len(results)
    successful = sum(1 for r in results if is_successful_progression(r))
    blocked = total - successful

    by_variant: Dict[str, List[VariantRunResult]] = {}
    for result in results:
        by_variant.setdefault(result.variant, []).append(result)

    variant_matrix: List[Dict[str, Any]] = []
    for variant, rows in sorted(by_variant.items(), key=lambda item: item[0]):
        pass_count = sum(1 for row in rows if is_successful_progression(row))
        avg_score = round(sum(row.diagnosis.score for row in rows) / len(rows), 2)
        variant_matrix.append(
            {
                "variant": variant,
                "runs": len(rows),
                "progressed_runs": pass_count,
                "blocked_runs": len(rows) - pass_count,
                "avg_smoking_gun_score": avg_score,
                "sample_verdict": rows[0].diagnosis.verdict if rows else "",
            }
        )

    signal_buckets: Dict[str, Dict[str, Any]] = {}
    for result in results:
        for signal in result.diagnosis.signals:
            bucket = signal_buckets.setdefault(
                signal.signal_id,
                {
                    "signal_id": signal.signal_id,
                    "severity": signal.severity,
                    "count": 0,
                    "weighted_strength": 0.0,
                    "variants": set(),
                    "finding": signal.finding,
                },
            )
            bucket["count"] += 1
            bucket["weighted_strength"] += (
                SEVERITY_POINTS.get(signal.severity, 0.0) * signal.confidence
            )
            bucket["variants"].add(result.variant)

    recurring_signals: List[Dict[str, Any]] = []
    for bucket in signal_buckets.values():
        recurring_signals.append(
            {
                "signal_id": bucket["signal_id"],
                "severity": bucket["severity"],
                "count": bucket["count"],
                "variants": sorted(bucket["variants"]),
                "weighted_strength": round(bucket["weighted_strength"], 2),
                "finding": bucket["finding"],
            }
        )

    recurring_signals.sort(
        key=lambda item: (item["weighted_strength"], item["count"]), reverse=True
    )
    recurring_ids = {item["signal_id"] for item in recurring_signals[:5]}

    if "ui_solved_but_backend_denied" in recurring_ids:
        conclusion = "Primary smoking gun: challenge UI completion does not grant backend acceptance (server-side trust rejection)."
    elif "webdriver_exposed" in recurring_ids:
        conclusion = "Primary smoking gun: webdriver exposure is consistently detected."
    elif "headless_ua_token" in recurring_ids:
        conclusion = "Primary smoking gun: headless UA token remains visible."
    elif "cloudflare_rate_or_loop" in recurring_ids:
        conclusion = (
            "Primary smoking gun: Cloudflare/rate reputation loop dominates outcomes."
        )
    elif blocked == 0:
        conclusion = "No blocking pattern detected in this run set."
    else:
        conclusion = (
            "Layered blocking persists; no single dominant trigger across all runs."
        )

    return SuiteSummary(
        utc_now_iso(),
        url,
        total,
        successful,
        blocked,
        variant_matrix,
        recurring_signals,
        conclusion,
    )


def write_markdown_summary(
    path: Path, summary: SuiteSummary, results: List[VariantRunResult]
) -> None:
    lines: List[str] = [
        "# ZoomInfo Diagnostics Summary",
        "",
        f"- Generated (UTC): `{summary.generated_utc}`",
        f"- Target URL: `{summary.url}`",
        f"- Total runs: **{summary.total_runs}**",
        f"- Progressed runs: **{summary.successful_runs}**",
        f"- Blocked runs: **{summary.blocked_runs}**",
        "",
        f"## Strongest Conclusion\n{summary.strongest_conclusion}",
        "",
        "## Variant Matrix",
        "| Variant | Runs | Progressed | Blocked | Avg Score |",
        "|---|---:|---:|---:|---:|",
    ]

    for row in summary.variant_matrix:
        lines.append(
            f"| {row['variant']} | {row['runs']} | {row['progressed_runs']} | {row['blocked_runs']} | {row['avg_smoking_gun_score']} |"
        )

    lines += [
        "",
        "## Top Recurring Signals",
        "| Signal | Severity | Count | Weighted Strength | Variants |",
        "|---|---|---:|---:|---|",
    ]

    for signal in summary.recurring_signals[:12]:
        lines.append(
            f"| {signal['signal_id']} | {signal['severity']} | {signal['count']} | {signal['weighted_strength']} | {', '.join(signal['variants'])} |"
        )

    lines += [
        "",
        "## Run-Level Verdicts",
        "| Variant | Run | Initial | Revisit | Final Title | Likely Real | Marker Soft | Score | Top Signal |",
        "|---|---:|---:|---:|---|---|---|---:|---|",
    ]

    for result in results:
        top_signal = (
            result.diagnosis.signals[0].signal_id
            if result.diagnosis.signals
            else "none"
        )
        final_title = str(result.final_state.get("title", "")).replace("|", "/")
        likely_real = bool(result.final_state.get("likely_real_page", False))
        marker_soft = bool(result.final_state.get("marker_soft_signal_only", False))
        lines.append(
            f"| {result.variant} | {result.run_index} | {result.initial_nav.get('status')} | {result.revisit_nav.get('status')} | {final_title} | {likely_real} | {marker_soft} | {result.diagnosis.score} | {top_signal} |"
        )

    path.write_text("\n".join(lines), encoding="utf-8")


def _is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0


async def run_variant_once(
    variant: VariantConfig,
    url: str,
    out_dir: Path,
    run_index: int,
    headless: bool,
    timeout_ms: int,
    hold_method: str,
    hold_seconds: float,
    pre_hold_wait_seconds: int,
    observe_seconds: int,
    skip_hold: bool,
    max_event_log: int,
    browser_name: str = "chrome",
) -> VariantRunResult:
    started_utc = utc_now_iso()
    event_log: List[Dict[str, Any]] = []

    # Mirroring true bypass behavior: ALWAYS use a fresh temp profile
    temp_profile_dir = tempfile.mkdtemp(prefix="codex_zi_bypass_")
    debug_port = 9222

    browser_path = os.environ.get("BROWSER_PATH") or _find_browser(browser_name)
    log(f"    [*] Launching genuine {browser_name.title()}: {browser_path}")

    launch_args = [
        browser_path,
        f"--remote-debugging-port={debug_port}",
        f"--user-data-dir={temp_profile_dir}",
        "--start-maximized",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-sync",
        url,  # Navigate directly as native browser
    ]

    if headless:
        launch_args.append("--headless")

    browser_proc = subprocess.Popen(
        launch_args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    log("    [*] Waiting for browser debug port...")
    for _ in range(30):
        if _is_port_open(debug_port):
            break
        await asyncio.sleep(0.5)
    else:
        log("    [-] Browser debug port never opened.")
        browser_proc.kill()
        raise RuntimeError("Browser debug port timeout")

    log("    [*] Waiting 8s for native challenge solving...")
    await asyncio.sleep(8)

    async with async_playwright() as p:
        log("    [*] Connecting Playwright over CDP...")
        browser = await p.chromium.connect_over_cdp(f"http://localhost:{debug_port}")

        contexts = browser.contexts
        if not contexts:
            log("    [-] No browser contexts found.")
            raise RuntimeError("No browser contexts")

        context = contexts[0]
        pages = context.pages
        page = pages[0] if pages else await context.new_page()

        # bypass_match: targeted tracker blocking
        if variant.name == "bypass_match":
            for tracker_domain in TRACKER_DOMAINS:
                await context.route(
                    f"**/*{tracker_domain}*",
                    lambda route: asyncio.ensure_future(route.abort()),
                )

        request_handler, response_handler = attach_event_watchers(
            page, url, event_log, max_event_log
        )

        try:
            # We don't have the initial_nav from the native load, so create a dummy one
            initial_nav = {
                "stage": "initial",
                "status": None,
                "url": page.url,
                "title": await safe_title(page),
            }
            initial_state = await wait_for_challenge_or_terminal(
                page, pre_hold_wait_seconds
            )
            fingerprint_before = await collect_fingerprint(page)
            cookies_initial = focused_cookies(await context.cookies(url))

            hold = HoldAttempt(
                False, "none", hold_seconds, None, None, False, "Hold skipped."
            )
            if (
                not skip_hold
                and not headless
                and initial_state.get("press_hold_visible")
            ):
                resolved_method = hold_method
                if hold_method == "auto":
                    resolved_method = "os" if HAS_PYAUTOGUI else "playwright"
                hold = await (
                    attempt_os_hold(page, hold_seconds)
                    if resolved_method == "os"
                    else attempt_playwright_hold(page, hold_seconds)
                )
            elif headless:
                hold.error = "Hold skipped in headless mode."
            elif not initial_state.get("press_hold_visible"):
                hold.error = "No visible Press & Hold challenge to interact with."

            # Post-hold settle: let PX complete its async clearance flow
            # (POST telemetry → receive clearance → set cookies → trigger redirect)
            if hold.attempted and hold.completed_marker_seen:
                log("    [*] Hold completed, settling 5s for PX clearance flow...")
                await asyncio.sleep(5.0)

            post_hold_state = await detect_challenge_state(page)
            post_hold_fetch_status = await fetch_status_with_credentials(page, url)
            cookies_post_hold = focused_cookies(await context.cookies(url))

            # For bypass_match: use reload() instead of goto() for revisit
            if (
                variant.name == "bypass_match"
                and hold.attempted
                and hold.completed_marker_seen
            ):
                log(
                    "    [*] bypass_match: using page.reload() for revisit (preserves cookie context)"
                )
                try:
                    await page.reload(wait_until="domcontentloaded", timeout=timeout_ms)
                except Exception:
                    pass
                revisit_nav_data = {
                    "stage": "revisit",
                    "status": None,
                    "url": page.url,
                    "title": await safe_title(page),
                    "error": None,
                    "request_headers": {},
                    "response_headers": {},
                    "request_cookie_names": [],
                    "response_server": None,
                    "response_cf_ray": None,
                }
                revisit_nav = revisit_nav_data
            else:
                revisit_nav = await capture_main_nav(page, url, timeout_ms, "revisit")
            observe = await observe_titles(page, observe_seconds)
            final_state = await detect_challenge_state(page)
            fingerprint_after = await collect_fingerprint(page)
            cookies_final = focused_cookies(await context.cookies(url))

            screenshot_path = out_dir / f"{variant.name}__run{run_index}__final.png"
            await page.screenshot(path=str(screenshot_path), full_page=True)

            preliminary = VariantRunResult(
                variant=variant.name,
                run_index=run_index,
                started_utc=started_utc,
                config=asdict(variant),
                initial_nav=initial_nav,
                initial_state=initial_state,
                fingerprint_before=fingerprint_before,
                hold=hold,
                post_hold_state=post_hold_state,
                post_hold_fetch_status=post_hold_fetch_status,
                revisit_nav=revisit_nav,
                observe_titles=observe,
                final_state=final_state,
                fingerprint_after=fingerprint_after,
                cookies_initial=cookies_initial,
                cookies_post_hold=cookies_post_hold,
                cookies_final=cookies_final,
                event_log=event_log,
                screenshot_path=str(screenshot_path),
                diagnosis=VariantDiagnosis(0.0, "", []),
            )

            preliminary.diagnosis = diagnose_run(preliminary)
            return preliminary
        finally:
            try:
                page.remove_listener("request", request_handler)
            except Exception:
                pass
            try:
                page.remove_listener("response", response_handler)
            except Exception:
                pass

            if browser is not None:
                try:
                    await browser.close()
                except Exception:
                    pass

            try:
                browser_proc.terminate()
                browser_proc.wait(timeout=5)
            except Exception:
                browser_proc.kill()

            if temp_profile_dir:
                shutil.rmtree(temp_profile_dir, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ZoomInfo diagnostics + smoking-gun analyzer."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Target URL.")
    parser.add_argument(
        "--variants",
        default="baseline,minimal_stealth,legacy_stealth",
        help="Comma list from: baseline,minimal_stealth,legacy_stealth,persistent_minimal,persistent_legacy",
    )
    parser.add_argument(
        "--runs-per-variant", type=int, default=1, help="Repeat count per variant."
    )
    parser.add_argument(
        "--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory."
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run headless (hold interactions skipped).",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=90000,
        help="Navigation timeout in milliseconds.",
    )
    parser.add_argument(
        "--hold-method",
        choices=["auto", "playwright", "os"],
        default="auto",
        help="Hold method. auto => os when available, otherwise playwright.",
    )
    parser.add_argument(
        "--hold-seconds", type=float, default=12.0, help="Seconds to hold Press & Hold."
    )
    parser.add_argument(
        "--pre-hold-wait-seconds",
        type=int,
        default=12,
        help="Wait after initial nav for challenge to appear.",
    )
    parser.add_argument(
        "--observe-seconds",
        type=int,
        default=15,
        help="Title observation duration after revisit.",
    )
    parser.add_argument(
        "--skip-hold", action="store_true", help="Skip hold interaction attempts."
    )
    parser.add_argument(
        "--max-event-log", type=int, default=300, help="Per-run event log cap."
    )
    parser.add_argument(
        "--no-scrub-cache",
        action="store_true",
        help="Disable __pycache__ cleanup at startup.",
    )
    parser.add_argument(
        "--browser",
        choices=["chrome", "edge"],
        default="chrome",
        help="Browser channel to use.",
    )
    return parser.parse_args()


async def async_main() -> int:
    args = parse_args()
    if args.runs_per_variant < 1:
        log("[-] --runs-per-variant must be >= 1")
        return 2

    script_dir = Path(__file__).resolve().parent
    out_dir = Path(args.out_dir).resolve()
    ensure_dir(out_dir)

    if not args.no_scrub_cache:
        removed = scrub_pycache(script_dir)
        log(f"[*] Cache scrub complete: removed {removed} '__pycache__' directories.")

    variants_map = default_variants()
    selected_names = [name.strip() for name in args.variants.split(",") if name.strip()]
    unknown = [name for name in selected_names if name not in variants_map]
    if unknown:
        log(f"[-] Unknown variants: {unknown}")
        log(f"[-] Valid variants: {sorted(variants_map.keys())}")
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = out_dir / f"run_{stamp}"
    ensure_dir(run_dir)

    results: List[VariantRunResult] = []
    total_jobs = len(selected_names) * args.runs_per_variant
    job_index = 0

    for variant_name in selected_names:
        variant = variants_map[variant_name]
        for run_index in range(1, args.runs_per_variant + 1):
            job_index += 1
            log(f"\n[*] Job {job_index}/{total_jobs}: {variant.name} run {run_index}")
            log(f"    {variant.description}")

            result = await run_variant_once(
                variant,
                args.url,
                run_dir,
                run_index,
                args.headless,
                args.timeout_ms,
                args.hold_method,
                args.hold_seconds,
                args.pre_hold_wait_seconds,
                args.observe_seconds,
                args.skip_hold,
                args.max_event_log,
                args.browser,
            )
            results.append(result)

            progressed = is_successful_progression(result)
            status_flag = "PASS" if progressed else "BLOCKED"
            top_signal = (
                result.diagnosis.signals[0].signal_id
                if result.diagnosis.signals
                else "none"
            )
            log(
                f"    [{status_flag}] initial={result.initial_nav.get('status')} revisit={result.revisit_nav.get('status')} score={result.diagnosis.score}"
            )
            log(f"    Verdict: {result.diagnosis.verdict}")
            log(f"    Top signal: {top_signal}")
            log(
                "    Evidence: "
                f"likely_real={result.final_state.get('likely_real_page')} "
                f"marker_soft={result.final_state.get('marker_soft_signal_only')} "
                f"words={result.final_state.get('word_count_estimate')} "
                f"structure={result.final_state.get('structure_signal_count')} "
                f"len={result.final_state.get('content_length')}"
            )

    summary = build_suite_summary(args.url, results)

    payload = {
        "meta": {
            "generated_utc": utc_now_iso(),
            "tool": "zoominfo_diagnostic_matrix.py",
            "pyautogui_available": HAS_PYAUTOGUI,
            "args": vars(args),
        },
        "summary": asdict(summary),
        "results": [asdict(result) for result in results],
    }

    json_path = run_dir / "zoominfo_diagnostic_matrix_results.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    md_path = run_dir / "zoominfo_diagnostic_matrix_summary.md"
    write_markdown_summary(md_path, summary, results)

    log("\n[+] Outputs:")
    log(f"    JSON: {json_path}")
    log(f"    MD  : {md_path}")
    log(f"\n[+] Strongest conclusion: {summary.strongest_conclusion}")

    return 0 if summary.successful_runs > 0 else 1


def main() -> int:
    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:
        log("[-] Interrupted by user.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
