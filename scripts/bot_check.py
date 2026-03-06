# ./scripts/bot_check.py
"""
Run matrix-style browser fingerprint diagnostics against selected test pages.
Run: python ./scripts/bot_check.py --modes baseline,stealth --browsers chromium,pw_chrome
Inputs: CLI flags for browser/mode matrix, target URL, system browser preference, and output paths.
Outputs: JSON result set and optional HTML summary with per-run fingerprint/risk metadata.
Side effects: launches Playwright/system browsers and optionally captures screenshots to ./scripts/out.
Operational notes: testing-only utility for defensive diagnostics and environment validation.
"""

import argparse
import dataclasses
import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page


# =========================
# Constants (centralized)
# =========================

DEFAULT_TEST_URL = "https://example.com/"
DEFAULT_VIEWPORT = (1920, 1080)
DEFAULT_LOCALE = "en-US"
DEFAULT_TIMEZONE = "America/Denver"

DEFAULT_SITES = [
    # Public fingerprint / bot detection checkers (optional)
    "https://bot.sannysoft.com/",
    "https://pixelscan.net/",
    "https://fingerprintjs.com/demo",
    "https://abrahamjuliot.github.io/creepjs/",
]

COMMON_CHROME_PATHS_WINDOWS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Users\%USERNAME%\AppData\Local\Google\Chrome\Application\chrome.exe",
]

COMMON_CHROMIUM_PATHS_WINDOWS = [
    r"C:\Program Files\Chromium\Application\chrome.exe",
    r"C:\Program Files (x86)\Chromium\Application\chrome.exe",
]

COMMON_EDGE_PATHS_WINDOWS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

DEFAULT_TIMEOUT_MS = 45_000


# =========================
# Logging
# =========================


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )


# =========================
# Helpers
# =========================


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def which_any(candidates: List[str]) -> Optional[str]:
    for c in candidates:
        p = shutil.which(c)
        if p:
            return p
    return None


def expand_windows_path(p: str) -> str:
    if "%USERNAME%" in p:
        p = p.replace("%USERNAME%", os.environ.get("USERNAME", ""))
    return os.path.expandvars(p)


def find_system_browser_executable(prefer: str) -> Optional[str]:
    """
    prefer: 'chrome' | 'chromium' | 'edge'
    """
    system = platform.system().lower()
    if system == "windows":
        candidates = []
        if prefer == "chrome":
            candidates += [expand_windows_path(x) for x in COMMON_CHROME_PATHS_WINDOWS]
        elif prefer == "chromium":
            candidates += [
                expand_windows_path(x) for x in COMMON_CHROMIUM_PATHS_WINDOWS
            ]
        elif prefer == "edge":
            candidates += [expand_windows_path(x) for x in COMMON_EDGE_PATHS_WINDOWS]
        for c in candidates:
            if c and Path(c).exists():
                return c
        # fallback to PATH
        if prefer == "chrome":
            return which_any(
                ["chrome", "google-chrome", "chrome.exe", "google-chrome.exe"]
            )
        if prefer == "chromium":
            return which_any(["chromium", "chromium-browser", "chromium.exe"])
        if prefer == "edge":
            return which_any(["msedge", "msedge.exe"])
        return None

    # Linux/mac: rely on PATH
    if prefer == "chrome":
        return which_any(["google-chrome", "google-chrome-stable", "chrome"])
    if prefer == "chromium":
        return which_any(["chromium", "chromium-browser"])
    if prefer == "edge":
        return which_any(["microsoft-edge", "microsoft-edge-stable", "msedge"])
    return None


# =========================
# Stealth init scripts (minimal + sane)
# =========================

STEALTH_INIT_JS = r"""
(() => {
  // 1) webdriver (delete from prototype is completely undetectable)
  try {
    delete Object.getPrototypeOf(navigator).webdriver;
  } catch (e) {}

  // 2) languages
  try {
    Object.defineProperty(navigator, 'languages', { get: () => Object.freeze(['en-US', 'en']) });
  } catch (e) {}

  // 3) chrome runtime object (some detectors expect it in Chrome)
  try {
    if (!window.chrome) window.chrome = {};
    if (!window.chrome.runtime) {
      window.chrome.runtime = {
        connect: () => {},
        sendMessage: () => {},
      };
    }
  } catch (e) {}

  // 4) permissions query: normalize notifications
  try {
    const originalQuery = window.navigator.permissions.query.bind(window.navigator.permissions);
    Object.defineProperty(navigator.permissions, 'query', {
      value: (parameters) => {
        if (parameters && parameters.name && parameters.name === 'notifications') {
          return Promise.resolve({ state: 'default' });
        }
        return originalQuery(parameters);
      }
    });
  } catch (e) {}

  // 5) Notification.permission
  try {
    Object.defineProperty(Notification, 'permission', { get: () => 'default' });
  } catch (e) {}

  // 6) plugins/mimeTypes: only override if empty
  try {
    if (navigator.plugins.length === 0) {
      const fakePluginArray = [
        { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 2 },
        { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 2 },
        { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 2 },
        { name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 2 },
        { name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 2 },
      ];
      Object.defineProperty(navigator, 'plugins', { get: () => fakePluginArray });
      Object.defineProperty(navigator, 'mimeTypes', { get: () => [{ type: 'application/pdf', suffixes: 'pdf', description: '' }] });
    }
  } catch (e) {}

  // 7) maxTouchPoints — Playwright overrides to 10, real non-touch is 0
  try {
    Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
  } catch (e) {}
})();
"""


# =========================
# Fingerprint JS payload
# =========================

FP_COLLECT_JS = r"""
(async () => {
  const out = {};
  const nav = navigator;

  // Basic navigator
  out.ua = nav.userAgent;
  out.webdriver = !!nav.webdriver;
  out.languages = nav.languages ? Array.from(nav.languages) : null;
  out.language = nav.language || null;
  out.platform = nav.platform || null;
  out.vendor = nav.vendor || null;
  out.deviceMemory = nav.deviceMemory || null;
  out.hardwareConcurrency = nav.hardwareConcurrency || null;
  out.maxTouchPoints = nav.maxTouchPoints || 0;

  // Timezone / locale
  try {
    out.tz = Intl.DateTimeFormat().resolvedOptions().timeZone || null;
    out.locale = Intl.DateTimeFormat().resolvedOptions().locale || null;
    out.offsetMinutes = new Date().getTimezoneOffset();
  } catch (e) {
    out.tz = null;
    out.locale = null;
    out.offsetMinutes = null;
  }

  // Screen + viewport
  out.screen = {
    w: screen.width,
    h: screen.height,
    aw: screen.availWidth,
    ah: screen.availHeight,
    d: window.devicePixelRatio || null,
    cd: screen.colorDepth || null,
    pd: screen.pixelDepth || null
  };
  out.viewport = { w: window.innerWidth, h: window.innerHeight };

  // DNT (JS)
  out.dnt_js = nav.doNotTrack || null;

  // Permissions
  out.permissions = {};
  const permNames = ['notifications', 'geolocation', 'camera', 'microphone'];
  for (const name of permNames) {
    try {
      const res = await nav.permissions.query({ name });
      out.permissions[name] = res.state;
    } catch (e) {
      out.permissions[name] = 'error';
    }
  }

  // Plugins
  try {
    const pls = nav.plugins ? Array.from(nav.plugins) : [];
    out.plugins = pls.map(p => ({
      name: p.name,
      filename: p.filename,
      description: p.description,
      length: (p.length ?? null)
    }));
  } catch (e) {
    out.plugins = null;
  }

  // WebGL
  out.webgl = {};
  try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    if (gl) {
      const dbg = gl.getExtension('WEBGL_debug_renderer_info');
      out.webgl.vendor = dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR);
      out.webgl.renderer = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
      out.webgl.version = gl.getParameter(gl.VERSION);
      out.webgl.shading = gl.getParameter(gl.SHADING_LANGUAGE_VERSION);
    } else {
      out.webgl.vendor = null;
      out.webgl.renderer = null;
      out.webgl.version = null;
      out.webgl.shading = null;
    }
  } catch (e) {
    out.webgl = { error: String(e) };
  }

  // Canvas fingerprint (stable hash)
  out.canvas = {};
  try {
    const c = document.createElement('canvas');
    c.width = 300;
    c.height = 150;
    const ctx = c.getContext('2d');
    ctx.textBaseline = 'top';
    ctx.font = "16px 'Arial'";
    ctx.fillStyle = '#f60';
    ctx.fillRect(125, 1, 62, 20);
    ctx.fillStyle = '#069';
    ctx.fillText('fingerprint-lab: Roy', 2, 15);
    ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
    ctx.fillText('canvas-test', 4, 45);
    const dataUrl = c.toDataURL();
    out.canvas.dataLen = dataUrl.length;

    // small rolling hash32 (fast, deterministic)
    let h = 0;
    for (let i = 0; i < dataUrl.length; i++) {
      h = ((h << 5) - h) + dataUrl.charCodeAt(i);
      h |= 0;
    }
    out.canvas.hash32 = h >>> 0;
  } catch (e) {
    out.canvas = { error: String(e) };
  }

  // Audio fingerprint (very small, deterministic)
  out.audio = {};
  try {
    const AC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
    if (!AC) throw new Error('OfflineAudioContext not available');
    const ctx = new AC(1, 44100, 44100);
    const osc = ctx.createOscillator();
    osc.type = 'triangle';
    osc.frequency.value = 10000;
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -50;
    comp.knee.value = 40;
    comp.ratio.value = 12;
    comp.attack.value = 0;
    comp.release.value = 0.25;
    osc.connect(comp);
    comp.connect(ctx.destination);
    osc.start(0);
    const buf = await ctx.startRendering();
    const ch = buf.getChannelData(0);

    // sample a few points
    const sample0 = ch[0];
    let h = 0;
    const stride = 256;
    const max = Math.min(ch.length, 44100);
    for (let i = 0; i < max; i += stride) {
      const v = Math.floor((ch[i] + 1) * 100000);
      h = ((h << 5) - h) + v;
      h |= 0;
    }
    out.audio.sample0 = sample0;
    out.audio.len = ch.length;

    out.audio.hash32 = h >>> 0;
  } catch (e) {
    out.audio = { error: String(e) };
  }

  // UA-CH (high-signal sometimes)
  out.uaData = null;
  try {
    if (nav.userAgentData) {
      const brands = nav.userAgentData.brands || null;
      const mobile = nav.userAgentData.mobile || null;
      const platform = nav.userAgentData.platform || null;
      out.uaData = { brands, mobile, platform };
    }
  } catch (e) {
    out.uaData = { error: String(e) };
  }

  return out;
})();
"""


# =========================
# Data models
# =========================


@dataclass
class ModeConfig:
    name: str
    apply_stealth: bool
    viewport_width: int
    viewport_height: int
    locale: str
    timezone_id: str
    extra_http_headers: Optional[Dict[str, str]] = None
    args: Optional[List[str]] = None


@dataclass
class RunResult:
    run_id: str
    timestamp_utc: str
    browser_label: str
    browser_version: str
    mode: Dict[str, Any]
    runtime: Dict[str, Any]
    launch: Dict[str, Any]
    data: Dict[str, Any]
    risk_score: int
    score_breakdown: Dict[str, Any]
    fp_sha256: str


# =========================
# Risk scoring heuristics
# =========================


def risk_score(
    fp: Dict[str, Any],
    request_headers: Dict[str, str],
    mode: ModeConfig,
    browser_label: str,
) -> Tuple[int, Dict[str, Any]]:
    """
    0 = most human-like, 100 = most bot-like
    """
    score = 0
    reasons: Dict[str, Any] = {}

    def add(points: int, key: str, detail: Any) -> None:
        nonlocal score
        score += points
        reasons[key] = detail

    webdriver = fp.get("webdriver", None)
    if webdriver is True:
        add(
            45,
            "webdriver_true",
            "navigator.webdriver is true (primary automation tell)",
        )

    # Headless tells often map to viewport/screen mismatches or odd permissions.
    # We don't detect headless directly; infer from common anomalies.
    screen = fp.get("screen", {}) or {}
    viewport = fp.get("viewport", {}) or {}
    if screen and viewport:
        if viewport.get("w") and screen.get("w") and viewport["w"] > screen["w"]:
            add(8, "viewport_gt_screen", {"viewport": viewport, "screen": screen})

    # Plugins: empty plugins is suspicious for Chrome
    plugins = fp.get("plugins", None)
    if isinstance(plugins, list):
        if len(plugins) == 0 and "chrome" in browser_label:
            add(10, "empty_plugins", "navigator.plugins empty on Chrome-like browser")

    # Permissions: all 'prompt' can be okay, but 'error' is a red flag
    perms = fp.get("permissions", {}) or {}
    if any(v == "error" for v in perms.values()):
        add(8, "permissions_error", perms)

    # UA / Sec-CH-UA mismatch heuristic
    ua = fp.get("ua", "") or ""
    sch_ua = request_headers.get("sec-ch-ua", "")
    if ua and sch_ua:
        ua_has_chrome = "Chrome/" in ua
        sch_has_google = "Google Chrome" in sch_ua
        # Example: UA says Chrome but sec-ch-ua doesn't mention Google Chrome
        if ua_has_chrome and not sch_has_google and "chromium" not in browser_label:
            add(6, "ua_ch_mismatch", {"ua": ua, "sec-ch-ua": sch_ua})

    # WebGL sanity: some stealth scripts output impossible combos
    webgl = fp.get("webgl", {}) or {}
    renderer = (webgl.get("renderer") or "").lower()
    if "iris" in renderer and "hd graphics" in ua.lower():
        # weak heuristic: not always wrong, but can be suspicious
        add(
            4,
            "webgl_renderer_suspicious",
            {"vendor": webgl.get("vendor"), "renderer": webgl.get("renderer")},
        )

    # DNT usage: not always bad, but uncommon; slight nudge
    if request_headers.get("dnt") == "1":
        add(2, "dnt_header", "DNT=1 header present")

    # Locale/timezone mismatch heuristics
    tz = fp.get("tz")
    if tz and mode.timezone_id and tz != mode.timezone_id:
        add(8, "timezone_mismatch", {"js_tz": tz, "configured": mode.timezone_id})

    # Hardware "too perfect" is suspicious too; we only lightly score extremes
    hc = fp.get("hardwareConcurrency")
    dm = fp.get("deviceMemory")
    if hc is not None and (hc <= 1 or hc >= 64):
        add(3, "hardware_concurrency_extreme", hc)
    if dm is not None and (dm <= 1 or dm >= 64):
        add(3, "device_memory_extreme", dm)

    score = max(0, min(100, score))
    return score, reasons


# =========================
# Core runner
# =========================


def build_modes(
    viewport: Tuple[int, int], locale: str, timezone_id: str
) -> List[ModeConfig]:
    w, h = viewport
    return [
        ModeConfig(
            name="baseline",
            apply_stealth=False,
            viewport_width=w,
            viewport_height=h,
            locale=locale,
            timezone_id=timezone_id,
            extra_http_headers=None,
            args=None,
        ),
        ModeConfig(
            name="stealth",
            apply_stealth=True,
            viewport_width=w,
            viewport_height=h,
            locale=locale,
            timezone_id=timezone_id,
            extra_http_headers=None,
            args=None,
        ),
        ModeConfig(
            name="baseline_dnt_header",
            apply_stealth=False,
            viewport_width=w,
            viewport_height=h,
            locale=locale,
            timezone_id=timezone_id,
            extra_http_headers={"DNT": "1"},
            args=None,
        ),
        ModeConfig(
            name="stealth_dnt_header",
            apply_stealth=True,
            viewport_width=w,
            viewport_height=h,
            locale=locale,
            timezone_id=timezone_id,
            extra_http_headers={"DNT": "1"},
            args=None,
        ),
    ]


def get_runtime_info() -> Dict[str, Any]:
    return {
        "python_version": sys.version.split()[0],
        "python_platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
    }


def context_for_mode(
    browser: Browser, mode: ModeConfig, user_data_dir: Optional[str]
) -> BrowserContext:
    context_kwargs: Dict[str, Any] = {
        "viewport": {"width": mode.viewport_width, "height": mode.viewport_height},
        "locale": mode.locale,
        "timezone_id": mode.timezone_id,
        "ignore_https_errors": True,
    }
    if mode.extra_http_headers:
        context_kwargs["extra_http_headers"] = mode.extra_http_headers

    # If user_data_dir is set, we use persistent context (more human-like),
    # but in sync_api this is on launch_persistent_context not browser.new_context.
    # So we only support user_data_dir on chromium-based launch paths that allow it.
    # Here we return a normal context and handle persistent separately in launcher.
    return browser.new_context(**context_kwargs)


def collect_main_request_headers(page: Page) -> Dict[str, str]:
    # We capture via request event on first navigation.
    captured: Dict[str, str] = {}

    def on_request(req):
        nonlocal captured
        if not captured and req.is_navigation_request():
            captured = {k.lower(): v for k, v in req.headers.items()}

    page.on("request", on_request)
    return captured


def collect_main_response_headers(page: Page) -> Dict[str, str]:
    captured: Dict[str, str] = {}

    def on_response(resp):
        nonlocal captured
        req = resp.request
        if not captured and req.is_navigation_request():
            captured = {k.lower(): v for k, v in resp.headers.items()}

    page.on("response", on_response)
    return captured


def run_single(
    playwright,
    browser_label: str,
    mode: ModeConfig,
    test_url: str,
    headless: bool,
    out_dir: Path,
    system_chrome_path: Optional[str],
    user_data_dir: Optional[str],
    sites: Optional[List[str]],
    take_screenshots: bool,
) -> RunResult:
    run_id = f"{browser_label}__{mode.name}__{int(time.time() * 1000)}"
    logging.info(f"RUN {run_id}")

    runtime = get_runtime_info()
    launch_info: Dict[str, Any] = {
        "channel": None,
        "executable_path": None,
        "headless": headless,
    }

    # -------------------------
    # Launch browser
    # -------------------------
    browser = None
    persistent_context = None

    launch_args = mode.args or []
    if headless:
        # New headless mode is common; no extra args required.
        pass

    try:
        if browser_label == "chromium":
            browser = playwright.chromium.launch(headless=headless, args=launch_args)
            launch_info["channel"] = None

        elif browser_label == "pw_chrome":
            browser = playwright.chromium.launch(
                channel="chrome", headless=headless, args=launch_args
            )
            launch_info["channel"] = "chrome"

        elif browser_label == "system_chrome":
            if not system_chrome_path:
                raise RuntimeError(
                    "system_chrome selected but Chrome executable not found. Provide --chrome-path."
                )
            launch_info["channel"] = None
            launch_info["executable_path"] = system_chrome_path
            browser = playwright.chromium.launch(
                executable_path=system_chrome_path, headless=headless, args=launch_args
            )

        elif browser_label == "firefox":
            browser = playwright.firefox.launch(headless=headless, args=launch_args)

        else:
            raise ValueError(f"Unknown browser_label: {browser_label}")

        browser_version = browser.version

        # -------------------------
        # Context + stealth init
        # -------------------------
        context = context_for_mode(browser, mode, user_data_dir=None)
        if mode.apply_stealth and browser_label != "firefox":
            context.add_init_script(STEALTH_INIT_JS)

        # -------------------------
        # Page + capture headers
        # -------------------------
        page = context.new_page()
        main_req_headers_hook = collect_main_request_headers(page)
        main_resp_headers_hook = collect_main_response_headers(page)

        # Navigate primary URL
        page.goto(test_url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)
        # Ensure hooks have chance to capture
        page.wait_for_timeout(250)

        # Collect fingerprint
        js_fp = page.evaluate(FP_COLLECT_JS)

        # Best-effort captured headers (hooks fill these dicts in place)
        main_request_headers = main_req_headers_hook or {}
        main_response_headers = main_resp_headers_hook or {}

        # Optional: additional sites
        site_results: List[Dict[str, Any]] = []
        if sites:
            for i, url in enumerate(sites, start=1):
                try:
                    page.goto(
                        url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS
                    )
                    page.wait_for_timeout(500)
                    title = page.title()
                    site_results.append({"url": url, "title": title, "ok": True})
                    if take_screenshots:
                        shot = out_dir / f"{run_id}__site{i}.png"
                        page.screenshot(path=str(shot), full_page=True)
                except Exception as e:
                    site_results.append({"url": url, "ok": False, "error": str(e)})

        # Score
        score, breakdown = risk_score(js_fp, main_request_headers, mode, browser_label)

        # Build canonical fingerprint blob used for hashing
        fingerprint_blob = {
            "browser_label": browser_label,
            "browser_version": browser_version,
            "mode": dataclasses.asdict(mode),
            "runtime": runtime,
            "launch": launch_info,
            "main_request_headers": main_request_headers,
            "main_response_headers": main_response_headers,
            "js_fingerprint": js_fp,
            "site_results": site_results,
        }
        fp_hash = sha256_hex(
            json.dumps(fingerprint_blob, sort_keys=True).encode("utf-8")
        )

        result = RunResult(
            run_id=run_id,
            timestamp_utc=utc_now_iso(),
            browser_label=browser_label,
            browser_version=browser_version,
            mode=dataclasses.asdict(mode),
            runtime=runtime,
            launch=launch_info,
            data={
                "test_url": test_url,
                "main_request_headers": main_request_headers,
                "main_response_headers": main_response_headers,
                "js_fingerprint": js_fp,
                "site_results": site_results,
            },
            risk_score=score,
            score_breakdown=breakdown,
            fp_sha256=fp_hash,
        )

        return result

    finally:
        try:
            if persistent_context:
                persistent_context.close()
        except Exception:
            pass
        try:
            if browser:
                browser.close()
        except Exception:
            pass


def write_json(out_path: Path, results: List[RunResult]) -> None:
    payload = [dataclasses.asdict(r) for r in results]
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logging.info(f"Wrote {out_path}")


def write_html_summary(out_path: Path, results: List[RunResult]) -> None:
    # Simple HTML to eyeball runs quickly
    rows = []
    for r in results:
        rows.append(
            f"<tr>"
            f"<td>{r.timestamp_utc}</td>"
            f"<td>{r.browser_label}</td>"
            f"<td>{r.browser_version}</td>"
            f"<td>{r.mode['name']}</td>"
            f"<td>{r.risk_score}</td>"
            f"<td><code>{r.fp_sha256[:16]}…</code></td>"
            f"</tr>"
        )
    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Fingerprint Lab Summary</title>
  <style>
    body {{ font-family: Arial, sans-serif; padding: 16px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; font-size: 13px; }}
    th {{ background: #f3f3f3; text-align: left; }}
  </style>
</head>
<body>
  <h2>Fingerprint Lab Summary</h2>
  <table>
    <thead>
      <tr>
        <th>Timestamp (UTC)</th>
        <th>Browser</th>
        <th>Version</th>
        <th>Mode</th>
        <th>Risk</th>
        <th>FP Hash</th>
      </tr>
    </thead>
    <tbody>
      {"".join(rows)}
    </tbody>
  </table>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")
    logging.info(f"Wrote {out_path}")


# =========================
# CLI
# =========================


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Fingerprint Lab: multi-browser fingerprint + risk scoring harness."
    )
    p.add_argument(
        "--install",
        action="store_true",
        help="Install Playwright browsers (runs 'playwright install').",
    )
    p.add_argument("--out-dir", default="out", help="Output directory.")
    p.add_argument(
        "--out-json",
        default="",
        help="Output JSON path (default: out/results_<timestamp>.json).",
    )
    p.add_argument("--out-html", action="store_true", help="Also write HTML summary.")
    p.add_argument("--test-url", default=DEFAULT_TEST_URL, help="Primary URL to test.")
    p.add_argument(
        "--browsers",
        default="chromium,pw_chrome,system_chrome,firefox",
        help="Comma list: chromium,pw_chrome,system_chrome,firefox",
    )
    p.add_argument(
        "--modes",
        default="all",
        help="all or comma list: baseline,stealth,baseline_dnt_header,stealth_dnt_header",
    )
    p.add_argument("--headless", action="store_true", help="Run headless.")
    p.add_argument("--viewport", default="1920x1080", help="Viewport like 1920x1080")
    p.add_argument("--locale", default=DEFAULT_LOCALE, help="Locale like en-US")
    p.add_argument(
        "--timezone", default=DEFAULT_TIMEZONE, help="Timezone like America/Denver"
    )
    p.add_argument(
        "--chrome-path",
        default="",
        help="Explicit Chrome executable path for system_chrome.",
    )
    p.add_argument(
        "--prefer-system",
        default="chrome",
        choices=["chrome", "chromium", "edge"],
        help="If --chrome-path not provided, try to find this browser executable.",
    )
    p.add_argument(
        "--sites", default="", help="Comma list of extra sites to visit (optional)."
    )
    p.add_argument(
        "--use-default-sites",
        action="store_true",
        help="Visit default detector sites list.",
    )
    p.add_argument(
        "--screenshots",
        action="store_true",
        help="Take screenshots for extra sites (saved in out-dir).",
    )
    p.add_argument("--verbose", action="store_true", help="Verbose logging.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)

    if args.install:
        code, out, err = run_cmd([sys.executable, "-m", "playwright", "install"])
        logging.info(out)
        if err:
            logging.warning(err)
        return code

    # Parse viewport
    try:
        vw, vh = args.viewport.lower().split("x")
        viewport = (int(vw), int(vh))
    except Exception:
        raise SystemExit("--viewport must be like 1920x1080")

    # Determine modes
    all_modes = build_modes(viewport, args.locale, args.timezone)
    modes_map = {m.name: m for m in all_modes}
    if args.modes == "all":
        modes = all_modes
    else:
        requested = [x.strip() for x in args.modes.split(",") if x.strip()]
        unknown = [x for x in requested if x not in modes_map]
        if unknown:
            raise SystemExit(
                f"Unknown modes: {unknown}. Valid: {list(modes_map.keys())}"
            )
        modes = [modes_map[x] for x in requested]

    # Determine browsers
    browsers = [x.strip() for x in args.browsers.split(",") if x.strip()]
    valid_b = {"chromium", "pw_chrome", "system_chrome", "firefox"}
    unknown_b = [b for b in browsers if b not in valid_b]
    if unknown_b:
        raise SystemExit(f"Unknown browsers: {unknown_b}. Valid: {sorted(valid_b)}")

    # Resolve system chrome path (only used for system_chrome)
    chrome_path = args.chrome_path.strip() or None
    if not chrome_path and "system_chrome" in browsers:
        chrome_path = find_system_browser_executable(args.prefer_system)
        if chrome_path:
            logging.info(f"Detected system browser executable: {chrome_path}")
        else:
            logging.warning(
                "Could not auto-detect system browser executable. system_chrome runs will fail unless --chrome-path is set."
            )

    # Sites
    sites: Optional[List[str]] = None
    if args.use_default_sites:
        sites = list(DEFAULT_SITES)
    if args.sites.strip():
        extra = [x.strip() for x in args.sites.split(",") if x.strip()]
        sites = (sites or []) + extra
    if sites:
        logging.info(f"Extra sites enabled: {len(sites)}")

    # Output paths
    out_dir = Path(args.out_dir)
    safe_mkdir(out_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_json = (
        Path(args.out_json) if args.out_json else (out_dir / f"results_{ts}.json")
    )
    out_html = out_dir / f"results_{ts}.html"

    results: List[RunResult] = []
    with sync_playwright() as pw:
        for b in browsers:
            for m in modes:
                try:
                    r = run_single(
                        playwright=pw,
                        browser_label=b,
                        mode=m,
                        test_url=args.test_url,
                        headless=args.headless,
                        out_dir=out_dir,
                        system_chrome_path=chrome_path,
                        user_data_dir=None,
                        sites=sites,
                        take_screenshots=args.screenshots,
                    )
                    results.append(r)
                    logging.info(
                        f"OK {b} {m.name} | risk={r.risk_score} | fp={r.fp_sha256[:16]}…"
                    )
                except Exception as e:
                    logging.error(f"FAIL {b} {m.name} :: {e}")

    write_json(out_json, results)
    if args.out_html:
        write_html_summary(out_html, results)

    # Print a small console summary
    if results:
        best = sorted(results, key=lambda x: x.risk_score)[0]
        worst = sorted(results, key=lambda x: x.risk_score)[-1]
        logging.info(
            f"BEST: {best.browser_label} {best.mode['name']} risk={best.risk_score} fp={best.fp_sha256[:16]}…"
        )
        logging.info(
            f"WORST: {worst.browser_label} {worst.mode['name']} risk={worst.risk_score} fp={worst.fp_sha256[:16]}…"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
