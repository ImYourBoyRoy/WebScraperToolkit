# ./scripts/get_browser_info.py
"""
Collect browser and JS fingerprint telemetry across baseline/stealth browser variants.
Run: python ./scripts/get_browser_info.py
Inputs: built-in mode matrix, Playwright channels, and optional CHROME_PATH environment variable.
Outputs: JSON payload printed to stdout with request headers and fingerprint highlights.
Side effects: launches local browser sessions (headed) for each variant.
Operational notes: diagnostic utility for controlled testing and fingerprint comparison.
"""

import asyncio
import json
import hashlib
import platform
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, List
from pathlib import Path
import os
from playwright.async_api import (
    async_playwright,
    BrowserType,
    Browser,
    BrowserContext,
    Page,
)

# playwright-stealth (Python) v2+
from playwright_stealth.stealth import Stealth

stealth = (
    Stealth()
)  # or Stealth(**ALL_EVASIONS_DISABLED_KWARGS) if you want everything off initially


def find_system_chrome_executable() -> Optional[str]:
    candidates = [
        os.environ.get("CHROME_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        # per-user install location (common)
        str(Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe"),
    ]
    for c in candidates:
        if c and Path(c).is_file():
            return c
    return None


FP_SCRIPT = r"""
() => {
  const out = {};

  // Navigator basics
  out.ua = navigator.userAgent;
  out.webdriver = navigator.webdriver;
  out.languages = navigator.languages;
  out.language = navigator.language;
  out.platform = navigator.platform;
  out.vendor = navigator.vendor;

  // Privacy-ish
  out.dnt_js = navigator.doNotTrack;

  // Hardware-ish
  out.hw = navigator.hardwareConcurrency;
  out.mem = navigator.deviceMemory;
  out.maxTouchPoints = navigator.maxTouchPoints;

  // Timezone/locale
  out.tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  out.locale = Intl.DateTimeFormat().resolvedOptions().locale;
  out.offset = new Date().getTimezoneOffset();

  // Screen/viewport
  out.screen = { w: screen.width, h: screen.height, d: devicePixelRatio, cd: screen.colorDepth };
  out.viewport = { w: innerWidth, h: innerHeight };

  // Plugins
  out.plugins = [];
  try {
    for (let i = 0; i < navigator.plugins.length; i++) {
      const p = navigator.plugins[i];
      out.plugins.push({
        name: p.name,
        filename: p.filename,
        description: p.description,
        length: p.length
      });
    }
  } catch (e) {
    out.plugins_error = String(e);
  }

  // WebGL vendor/renderer
  out.webgl = null;
  try {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
    if (gl) {
      const dbg = gl.getExtension("WEBGL_debug_renderer_info");
      const vendor = dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR);
      const renderer = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
      out.webgl = {
        vendor,
        renderer,
        version: gl.getParameter(gl.VERSION),
        shading: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
      };
    }
  } catch (e) {
    out.webgl = { error: String(e) };
  }

  // Canvas cheap hash
  out.canvas = {};
  try {
    const c = document.createElement("canvas");
    c.width = 300; c.height = 150;
    const ctx = c.getContext("2d");
    ctx.textBaseline = "top";
    ctx.font = "16px Arial";
    ctx.fillStyle = "#f60";
    ctx.fillRect(10, 10, 100, 50);
    ctx.fillStyle = "#069";
    ctx.fillText("fingerprint_test_123", 10, 70);
    const data = c.toDataURL();
    out.canvas.dataLen = data.length;
    let h = 0;
    for (let i = 0; i < data.length; i++) h = (h * 31 + data.charCodeAt(i)) >>> 0;
    out.canvas.hash32 = h;
  } catch (e) {
    out.canvas = { error: String(e) };
  }

  return out;
}
"""

PERMS_SCRIPT = r"""
async (names) => {
  const out = {};
  if (!navigator.permissions || !navigator.permissions.query) {
    for (const n of names) out[n] = "unsupported";
    return out;
  }
  for (const n of names) {
    try {
      const st = await navigator.permissions.query({ name: n });
      out[n] = st.state;
    } catch {
      out[n] = "unsupported";
    }
  }
  return out;
}
"""

AUDIO_HASH_SCRIPT = r"""
async () => {
  const AC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  if (!AC) return { error: "OfflineAudioContext unsupported" };

  const ctx = new AC(1, 44100, 44100);
  const osc = ctx.createOscillator();
  osc.type = "triangle";
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
  const data = buf.getChannelData(0);

  let hash = 0;
  const step = 64;
  for (let i = 0; i < 5000; i += step) {
    const v = Math.floor((data[i] || 0) * 1e6);
    hash = (hash * 31 + v) >>> 0;
  }
  return { hash32: hash, sample0: data[0], len: data.length };
}
"""


@dataclass
class ModeConfig:
    name: str
    apply_stealth: bool = False
    viewport_width: int = 1920
    viewport_height: int = 1080
    locale: str = "en-US"
    timezone_id: str = "America/Denver"
    extra_http_headers: Optional[Dict[str, str]] = None
    args: Optional[List[str]] = None


def sha256_json(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


async def collect(page: Page, test_url: str) -> Dict[str, Any]:
    main_req_headers: Dict[str, str] = {}
    main_resp_headers: Dict[str, str] = {}

    def on_request(req):
        nonlocal main_req_headers
        if req.is_navigation_request() and req.frame == page.main_frame:
            if not main_req_headers:
                main_req_headers = dict(req.headers)

    async def on_response(resp):
        nonlocal main_resp_headers
        try:
            if (
                resp.request.is_navigation_request()
                and resp.request.frame == page.main_frame
            ):
                if not main_resp_headers:
                    main_resp_headers = dict(resp.headers)
        except Exception:
            pass

    page.on("request", on_request)
    page.on("response", lambda r: asyncio.create_task(on_response(r)))

    await page.goto(test_url, wait_until="domcontentloaded")

    fp = await page.evaluate(FP_SCRIPT)
    perms = await page.evaluate(
        PERMS_SCRIPT, ["notifications", "geolocation", "camera", "microphone"]
    )
    fp["permissions"] = perms

    audio = await page.evaluate(AUDIO_HASH_SCRIPT)
    fp["audio"] = audio

    return {
        "test_url": test_url,
        "main_request_headers": main_req_headers,
        "main_response_headers": main_resp_headers,
        "js_fingerprint": fp,
        "fp_sha256": sha256_json(fp),
    }


async def run_variant(
    browser_type: BrowserType,
    browser_label: str,
    channel: Optional[str],
    mode: ModeConfig,
    test_url: str,
    executable_path: Optional[str] = None,  # NEW
) -> Dict[str, Any]:
    launch_kwargs: Dict[str, Any] = {"headless": False}
    if channel:
        launch_kwargs["channel"] = channel
    if executable_path:
        launch_kwargs["executable_path"] = executable_path
    if mode.args:
        launch_kwargs["args"] = mode.args

    browser: Browser = await browser_type.launch(**launch_kwargs)

    context_kwargs: Dict[str, Any] = {
        "viewport": {"width": mode.viewport_width, "height": mode.viewport_height},
        "locale": mode.locale,
        "timezone_id": mode.timezone_id,
    }
    if mode.extra_http_headers:
        context_kwargs["extra_http_headers"] = mode.extra_http_headers

    context: BrowserContext = await browser.new_context(**context_kwargs)

    # Apply stealth as variant-under-test (prefer context-level so it affects all pages)
    if mode.apply_stealth:
        await stealth.apply_stealth_async(context)

    page = await context.new_page()

    data = await collect(page, test_url)

    # NOTE: In Playwright Python, browser.version is a string property, not a function.
    result = {
        "browser_label": browser_label,
        "mode": asdict(mode),
        "browser_version": browser.version,  # <-- fixed
        "runtime": {
            "python_platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
        },
        "launch": {"channel": channel},
        "data": data,
        "highlights": {
            "ua": data["js_fingerprint"].get("ua"),
            "webdriver": data["js_fingerprint"].get("webdriver"),
            "dnt_js": data["js_fingerprint"].get("dnt_js"),
            "webgl_vendor": (data["js_fingerprint"].get("webgl") or {}).get("vendor"),
            "webgl_renderer": (data["js_fingerprint"].get("webgl") or {}).get(
                "renderer"
            ),
            "canvas_hash32": (data["js_fingerprint"].get("canvas") or {}).get("hash32"),
            "audio_hash32": (data["js_fingerprint"].get("audio") or {}).get("hash32"),
        },
    }

    await context.close()
    await browser.close()
    return result


async def main():
    test_url = "https://example.com/"

    modes = [
        ModeConfig(name="baseline", apply_stealth=False),
        ModeConfig(name="stealth", apply_stealth=True),
        ModeConfig(
            name="baseline_dnt_header",
            apply_stealth=False,
            extra_http_headers={"DNT": "1"},
        ),
        ModeConfig(
            name="stealth_dnt_header",
            apply_stealth=True,
            extra_http_headers={"DNT": "1"},
        ),
    ]

    async with async_playwright() as p:
        results: List[Dict[str, Any]] = []

        system_chrome = find_system_chrome_executable()

        for mode in modes:
            # Bundled Chromium
            results.append(
                await run_variant(p.chromium, "chromium", None, mode, test_url)
            )

            # Playwright-managed Chrome channel
            try:
                results.append(
                    await run_variant(p.chromium, "pw_chrome", "chrome", mode, test_url)
                )
            except Exception as e:
                results.append(
                    {
                        "browser_label": "pw_chrome",
                        "mode": asdict(mode),
                        "error": f"{type(e).__name__}: {e}",
                        "hint": "Run: playwright install chrome",
                    }
                )

            # System-installed Chrome
            if system_chrome:
                try:
                    results.append(
                        await run_variant(
                            p.chromium,
                            "system_chrome",
                            channel=None,
                            mode=mode,
                            test_url=test_url,
                            executable_path=system_chrome,
                        )
                    )
                except Exception as e:
                    results.append(
                        {
                            "browser_label": "system_chrome",
                            "mode": asdict(mode),
                            "chrome_path": system_chrome,
                            "error": f"{type(e).__name__}: {e}",
                        }
                    )
            else:
                results.append(
                    {
                        "browser_label": "system_chrome",
                        "mode": asdict(mode),
                        "error": "Chrome executable not found",
                        "hint": "Set CHROME_PATH env var to your chrome.exe path",
                    }
                )

        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
