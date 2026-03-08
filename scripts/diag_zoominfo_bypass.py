# ./scripts/diag_zoominfo_bypass.py
"""
Target-Site Stealth Bypass Test — Subprocess Chrome/Edge + PyAutoGUI
====================================================================

Exercises anti-bot challenge solving by launching a genuine browser process
(Chrome or Edge), then connecting with Playwright CDP for observation only.
OS-level mouse events (pyautogui) are used for "Press & Hold" style challenges.

Run:  python ./scripts/diag_zoominfo_bypass.py [--browser chrome|edge] [--url https://target-site.tld/path]
Inputs:  --browser chrome (default) or --browser edge, plus --url target.
Outputs: Console logs, debug_px.txt network trace, target_debug.png screenshot.
Notes:   Must run HEADED with system Chrome or Edge installed.
         Will briefly control your real cursor during the hold.
         Move mouse to any screen corner to abort (pyautogui failsafe).
"""

import argparse
import asyncio
import ctypes
import os
import random
import shutil
import socket
import subprocess
import sys
import tempfile

# Force per-monitor DPI awareness BEFORE importing pyautogui.
# This ensures pyautogui uses physical device pixels, matching the
# coordinate system we compute after scaling by devicePixelRatio.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

import pyautogui
from playwright.async_api import async_playwright

# --- PyAutoGUI safety ---
pyautogui.FAILSAFE = True  # Move mouse to corner to abort
pyautogui.PAUSE = 0  # We manage our own timing

# --- Tracker domains to block (reduces fingerprinting surface) ---
_TRACKER_DOMAINS = [
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


def log_msg(msg: str) -> None:
    """Print and append to debug_px.txt."""
    try:
        print(msg)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe_msg = msg.encode(encoding, errors="replace").decode(
            encoding, errors="replace"
        )
        print(safe_msg)
    with open("debug_px.txt", "a", encoding="utf-8") as f:
        f.write(msg + "\n")


async def _get_browser_chrome_offset(page) -> dict:
    """Return browser window position, chrome height, and device pixel ratio."""
    return await page.evaluate("""() => ({
        screenX:  window.screenX,
        screenY:  window.screenY,
        outerH:   window.outerHeight,
        innerH:   window.innerHeight,
        chromeH:  window.outerHeight - window.innerHeight,
        dpr:      window.devicePixelRatio || 1
    })""")


def _viewport_to_screen(win_info: dict, vp_x: float, vp_y: float):
    """Translate viewport-relative (CSS) coords to absolute physical screen coords.

    Multiplies by devicePixelRatio so pyautogui (which operates in physical
    device pixels after SetProcessDpiAwareness) targets the correct position.
    """
    dpr = win_info.get("dpr", 1)
    return (
        (win_info["screenX"] + vp_x) * dpr,
        (win_info["screenY"] + win_info["chromeH"] + vp_y) * dpr,
    )


def _os_mouse_move(target_x: float, target_y: float, duration: float = 0.6) -> None:
    """Move the real OS cursor using a quadratic bezier curve for human-like trajectory."""
    start_x, start_y = pyautogui.position()

    # Generate a random control point for the curve
    cp_x = (
        start_x
        + (target_x - start_x) * random.uniform(0.3, 0.7)
        + random.uniform(-100, 100)
    )
    cp_y = (
        start_y
        + (target_y - start_y) * random.uniform(0.3, 0.7)
        + random.uniform(-100, 100)
    )

    steps = random.randint(20, 35)

    for i in range(1, steps + 1):
        t = i / steps
        # Easing function for t (ease-out cubic)
        t_eased = 1 - pow(1 - t, 3)

        # Quadratic bezier formula
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

        # Add tiny jitter
        jx = ix + random.uniform(-1, 1)
        jy = iy + random.uniform(-1, 1)

        # Calculate segmented duration relative to the total requested duration
        seg_duration = duration / steps

        pyautogui.moveTo(jx, jy, duration=seg_duration, _pause=False)

    # Snap exactly to center at the end
    pyautogui.moveTo(target_x, target_y, duration=0.1, _pause=False)


async def _os_click_element(page, locator) -> bool:
    """Click an element using the real OS mouse. Returns True on success."""
    box = await locator.first.bounding_box()
    if not box:
        return False
    win = await _get_browser_chrome_offset(page)
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    sx, sy = _viewport_to_screen(win, cx, cy)
    _os_mouse_move(sx, sy, duration=random.uniform(0.3, 0.6))
    pyautogui.click()
    return True


async def _check_challenge_completed(page) -> bool:
    """Check if 'Human Challenge completed' button exists in any frame."""
    for frame in page.frames:
        try:
            done_btn = frame.get_by_role("button", name="Human Challenge completed")
            if await done_btn.count() > 0:
                return True
        except Exception:
            continue
    return False


async def _find_smallest_hold_element(page):
    """Find the actual clickable PX button, not the container.

    PX captcha has a nested structure: the outer #px-captcha container is
    530x100, but the actual clickable button inside is ~253x50. We search
    for the SMALLEST matching element to ensure we center on the real button.
    """
    candidates = []

    for frame in page.frames:
        # Strategy 1: Inner button inside #px-captcha container
        try:
            inner_btn = frame.locator("#px-captcha button")
            if await inner_btn.count() > 0 and await inner_btn.first.is_visible():
                box = await inner_btn.first.bounding_box()
                if box and box["y"] < 2000:
                    candidates.append((inner_btn, box, "inner_button"))
        except Exception:
            pass

        # Strategy 2: ARIA button with exact "Press & Hold" name
        try:
            aria_btn = frame.get_by_role("button", name="Press & Hold")
            if await aria_btn.count() > 0 and await aria_btn.first.is_visible():
                box = await aria_btn.first.bounding_box()
                if box and box["y"] < 2000:
                    candidates.append((aria_btn, box, "aria_button"))
        except Exception:
            pass

        # Strategy 3: #px-captcha container (fallback)
        try:
            container = frame.locator("#px-captcha")
            if await container.count() > 0 and await container.first.is_visible():
                box = await container.first.bounding_box()
                if box and box["y"] < 2000:
                    candidates.append((container, box, "container"))
        except Exception:
            pass

    if not candidates:
        return None, None

    # Pick the SMALLEST bounding box — that's the actual clickable button
    candidates.sort(key=lambda c: c[1]["width"] * c[1]["height"])
    best_locator, best_box, best_strategy = candidates[0]

    log_msg(
        f"[*] Selected '{best_strategy}': {best_box['width']:.0f}x{best_box['height']:.0f} "
        f"at ({best_box['x']:.0f}, {best_box['y']:.0f}) "
        f"[{len(candidates)} candidates]"
    )

    return best_locator, best_box


async def _os_press_and_hold(page, hold_element, precomputed_box=None) -> bool:
    """Execute OS-level press-and-hold with dynamic completion detection.

    Holds the mouse button and polls the DOM for the 'Human Challenge completed'
    signal rather than using a fixed timer. Releases as soon as completion is
    detected, or after a 15s safety timeout.
    """
    # Bring page to top FIRST so the OS settles the window position
    # before we measure bounding box / screen coords.
    try:
        await page.bring_to_front()
    except Exception:
        pass
    await asyncio.sleep(0.3)  # let OS settle after focus change

    # Use precomputed box if available, otherwise re-fetch
    if precomputed_box:
        box = precomputed_box
    else:
        box = await hold_element.first.bounding_box()
    if not box:
        log_msg("[-] Could not get bounding box.")
        return False

    log_msg(
        f"[*] Bbox: x={box['x']:.0f} y={box['y']:.0f} w={box['width']:.0f} h={box['height']:.0f}"
    )

    win = await _get_browser_chrome_offset(page)
    dpr = win.get("dpr", 1)
    log_msg(
        f"[*] Window: screenX={win['screenX']:.0f} screenY={win['screenY']:.0f} "
        f"chromeH={win['chromeH']:.0f} outerH={win['outerH']:.0f} "
        f"innerH={win['innerH']:.0f} dpr={dpr}"
    )

    # Exact center — NO random jitter on the final target
    target_vx = box["x"] + box["width"] / 2
    target_vy = box["y"] + box["height"] / 2
    target_sx, target_sy = _viewport_to_screen(win, target_vx, target_vy)

    log_msg(
        f"[*] Target center: viewport ({target_vx:.0f}, {target_vy:.0f}) "
        f"→ screen ({target_sx:.0f}, {target_sy:.0f}) [dpr={dpr}]"
    )

    # Move to exactly the center of the button with a human-like curved path
    log_msg(f"[*] OS mouse → screen ({target_sx:.0f}, {target_sy:.0f})")

    # Optional: ensure starting position isn't exactly already there
    curr_x, curr_y = pyautogui.position()
    dist = ((curr_x - target_sx) ** 2 + (curr_y - target_sy) ** 2) ** 0.5
    if dist < 50:
        # Move away slightly to force a small curve approach
        pyautogui.moveTo(curr_x - 100, curr_y + random.randint(-50, 50), duration=0.2)
        await asyncio.sleep(0.1)

    _os_mouse_move(target_sx, target_sy, duration=random.uniform(0.5, 0.9))
    await asyncio.sleep(random.uniform(0.1, 0.25))

    # 3. Dynamic press-and-hold — poll for completion
    log_msg("[*] OS mouseDown — holding until challenge completes (max 15s)...")
    pyautogui.mouseDown()

    hold_start = asyncio.get_event_loop().time()
    challenge_completed = False
    max_hold = 15.0

    try:
        while True:
            # FIX 5: Randomize polling interval to avoid mechanical detection
            await asyncio.sleep(random.uniform(0.2, 0.5))
            elapsed = asyncio.get_event_loop().time() - hold_start

            # Poll for completion signal
            try:
                if await _check_challenge_completed(page):
                    challenge_completed = True
                    log_msg(f"[*] Challenge completed detected at {elapsed:.1f}s!")
                    break
            except Exception:
                pass

            # Check if px-captcha disappeared from all frames
            try:
                content = (await page.content()).lower()
                if "px-captcha" not in content and "press & hold" not in content:
                    challenge_completed = True
                    log_msg(f"[*] Challenge markers gone at {elapsed:.1f}s!")
                    break
            except Exception:
                challenge_completed = True
                log_msg(f"[*] Page detached at {elapsed:.1f}s — success.")
                break

            if elapsed >= max_hold:
                log_msg(
                    f"[-] Max hold time ({max_hold:.0f}s) reached without completion."
                )
                break
    finally:
        pyautogui.mouseUp()
        final_elapsed = asyncio.get_event_loop().time() - hold_start
        log_msg(f"[*] OS mouseUp after {final_elapsed:.1f}s.")

    # 4. Extended settle after release — PX needs time to:
    #    POST telemetry → receive clearance → set cookies → trigger redirect
    log_msg("[*] Settling 3.5s for PX clearance flow...")
    await asyncio.sleep(3.5)

    if challenge_completed:
        return True

    # Post-hold fallback checks
    try:
        content = (await page.content()).lower()
    except Exception:
        log_msg("[*] Page detached after hold — success.")
        return True

    if "px-captcha" not in content and "press & hold" not in content:
        log_msg("[*] No challenge markers in page — success.")
        return True

    if await _check_challenge_completed(page):
        log_msg("[*] 'Human Challenge completed' found post-hold!")
        return True

    for frame in page.frames:
        try:
            ph = frame.get_by_role("button", name="Press & Hold")
            if await ph.count() > 0 and await ph.first.is_visible():
                log_msg("[-] Press & Hold button still visible — hold failed.")
                return False
        except Exception:
            continue

    log_msg("[*] No challenge elements remain — success.")
    return True


async def solve_challenges(page, url: str) -> bool:
    """Poll frames for CF/PX challenges and solve them with OS-level mouse.

    Handles three challenge types:
    1. CloudFlare IUAM ("Just a moment...") — auto-resolves via JS, we just wait
    2. CloudFlare Turnstile checkbox — OS click
    3. PerimeterX "Press & Hold" — OS mouse hold

    After solving the PX challenge, waits for PX's natural page redirect.
    Falls back to forced navigation if needed.
    """
    log_msg("[*] Starting interaction loop to solve CF/PX challenges...")
    warmup_done = False  # FIX 4: Track whether behavioral warmup has been performed

    for attempt in range(90):
        try:
            # --- CloudFlare challenges (IUAM + Turnstile) ---
            try:
                title = await page.title()
                if "Just a moment" in title:
                    content = await page.content()
                    has_px = (
                        "px-captcha" in content.lower()
                        or "press & hold" in content.lower()
                    )

                    # Turnstile challenge — CF's managed challenge that auto-solves
                    # if the browser passes attestation. Needs extended wait time.
                    has_turnstile = (
                        "cf-turnstile" in content.lower()
                        or "challenges.cloudflare.com" in content.lower()
                        or "turnstile" in content.lower()
                    )

                    if has_turnstile and not has_px:
                        log_msg(
                            f"[*] CF Turnstile challenge detected (attempt {attempt + 1}), "
                            f"waiting for auto-solve..."
                        )
                        # Turnstile needs more time than IUAM — it runs proof-of-work
                        # and attestation checks. Give it 5s per attempt.
                        await asyncio.sleep(5)
                        continue

                    if not has_px and not has_turnstile:
                        log_msg(
                            f"[*] CF IUAM auto-challenge detected (attempt {attempt + 1}), waiting..."
                        )
                        await asyncio.sleep(2)
                        continue
            except Exception:
                pass

            for frame in page.frames:
                # --- Cloudflare Turnstile Checkbox (visible interactive variant) ---
                cf_checkbox = frame.locator(".ctp-checkbox-label")
                try:
                    if (
                        await cf_checkbox.count() > 0
                        and await cf_checkbox.first.is_visible()
                    ):
                        log_msg("[*] Found Cloudflare Checkbox — OS clicking...")
                        await _os_click_element(page, cf_checkbox)
                        await asyncio.sleep(3)
                        continue
                except Exception:
                    pass

                # --- Cloudflare Turnstile iframe checkbox input ---
                turnstile_input = frame.locator("input[type='checkbox']")
                try:
                    if (
                        "challenges.cloudflare.com" in (frame.url or "")
                        and await turnstile_input.count() > 0
                        and await turnstile_input.first.is_visible()
                    ):
                        log_msg(
                            "[*] Found Turnstile checkbox in iframe — OS clicking..."
                        )
                        await _os_click_element(page, turnstile_input)
                        await asyncio.sleep(3)
                        continue
                except Exception:
                    pass

            # --- Find PX Press & Hold button (smallest matching element) ---
            hold_element, hold_box = await _find_smallest_hold_element(page)

            if hold_element:
                log_msg("[*] Found 'Press & Hold' challenge!")

                # FIX 4: Behavioral warmup — simulate human browsing before
                # interacting with the challenge. PX scores behavioral patterns;
                # jumping straight to the button is a bot signal.
                if not warmup_done:
                    warmup_done = True
                    log_msg(
                        "[*] Running behavioral warmup (scroll + mouse movement)..."
                    )
                    try:
                        # Use OS-level mouse only: Playwright page.mouse leaks CDP bot signals
                        _os_mouse_move(
                            random.randint(200, 600),
                            random.randint(200, 400),
                            duration=random.uniform(0.6, 1.2),
                        )
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                        # Scroll slightly down (negative int in PyAutoGUI Windows)
                        pyautogui.scroll(random.randint(-150, -50))
                        await asyncio.sleep(random.uniform(0.3, 0.8))
                        _os_mouse_move(
                            random.randint(100, 500),
                            random.randint(150, 350),
                            duration=random.uniform(0.6, 1.2),
                        )
                        await asyncio.sleep(random.uniform(0.4, 1.0))
                    except Exception:
                        pass  # warmup is best-effort, don't fail the run

                ok = await _os_press_and_hold(
                    page, hold_element, precomputed_box=hold_box
                )
                if ok:
                    log_msg(
                        "[+] PX challenge PASSED! Waiting for natural page transition..."
                    )

                    # Wait for PX's own JS redirect
                    real_page = await _wait_for_real_page(page, url)
                    if real_page:
                        return True

                    # Fallback: Check if PX clearance cookies exist before retry
                    cookies = await page.context.cookies()
                    px_cookies = [c for c in cookies if c["name"].startswith("_px")]
                    log_msg(
                        f"[*] PX cookies after challenge: {[c['name'] for c in px_cookies]}"
                    )

                    # Use reload() to preserve cookie context, NOT goto() which
                    # creates a fresh navigation that PX evaluates independently
                    log_msg("[*] Natural redirect timed out, trying page.reload()...")
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=20000)
                    except Exception as nav_err:
                        log_msg(f"[!] Reload error (may be OK): {nav_err}")
                    await asyncio.sleep(3)
                    return await _verify_real_page(page, url)
                else:
                    log_msg("[-] Press & Hold attempt failed, will retry...")
                    await asyncio.sleep(2)
                    continue

        except Exception as exc:
            log_msg(f"[!] Transient error: {type(exc).__name__}: {exc}")

        # --- Check if we already passed (no challenge present) ---
        try:
            title = await page.title()
            page_url = page.url
            if (
                page_url.startswith("http")
                and "just a moment" not in title.lower()
                and "access denied" not in title.lower()
            ):
                content = await page.content()
                if (
                    "px-captcha" not in content.lower()
                    and "press & hold" not in content.lower()
                ):
                    log_msg(f"[+] Page loaded directly! Title: {title}")
                    return True
        except Exception:
            pass

        await asyncio.sleep(1)

    log_msg("[-] Challenge solving loop timed out.")
    return False


async def _wait_for_real_page(page, url: str, timeout: float = 20.0) -> bool:
    """Wait for PX's JS to naturally redirect the page after challenge solve.

    PX sets a clearance cookie and then auto-redirects via JS. This function
    polls with lightweight title checks (avoiding heavy page.content() calls
    that can interfere with PX's JS execution) and only fetches content once
    the title changes.

    Returns True if the real page loaded within the timeout.
    """
    log_msg(f"[*] Waiting up to {timeout:.0f}s for natural page transition...")
    start = asyncio.get_event_loop().time()
    last_title = ""

    while asyncio.get_event_loop().time() - start < timeout:
        await asyncio.sleep(2.0)  # Less aggressive polling — let PX's JS work
        try:
            title = await page.title()
            elapsed = asyncio.get_event_loop().time() - start

            # Detect title change (PX redirect will change the page title)
            if title != last_title:
                last_title = title
                log_msg(f"[*] Title at {elapsed:.1f}s: '{title}'")

            # Skip content check if still on access denied
            if (
                "access denied" in title.lower()
                or "access to this page" in title.lower()
            ):
                continue

            if "Just a moment" in title:
                continue

            # Title changed to something promising — do a full content check
            content = await page.content()
            if "company-name" in content:
                log_msg(f"[+] Natural transition: real page detected! Title: {title}")
                return True

            if (
                "px-captcha" not in content.lower()
                and "press & hold" not in content.lower()
            ):
                if page.url.startswith("http"):
                    log_msg(
                        f"[*] Page transitioned (title: {title}), no challenge markers."
                    )
                    return True

        except Exception:
            continue

    log_msg("[-] Natural page transition timed out.")
    return False


async def _verify_real_page(page, url: str) -> bool:
    """Verify the target page loaded after forced navigation."""
    for retry in range(3):
        try:
            title = await page.title()
            content = await page.content()
            page_url = page.url
            log_msg(f"[*] Verify attempt {retry + 1}: title='{title}' url={page_url}")

            if "company-name" in content:
                log_msg("[+] Real page content detected (.company-name found)!")
                return True

            if "px-captcha" in content.lower() or "press & hold" in content.lower():
                log_msg("[!] Challenge still present after re-navigation.")
                return False

            if (
                "access denied" in title.lower()
                or "access to this page" in content.lower()
            ):
                log_msg(
                    f"[!] Access denied on attempt {retry + 1}, waiting before retry..."
                )
                await asyncio.sleep(3)
                try:
                    # Use reload() to preserve cookie context
                    await page.reload(wait_until="domcontentloaded", timeout=20000)
                except Exception:
                    pass
                await asyncio.sleep(2)
                continue

            if "Just a moment" not in title and "Access" not in title:
                log_msg(f"[*] Page loaded (title: {title}) but no .company-name class.")
                return True

        except Exception as exc:
            log_msg(f"[!] Verify error: {exc}")

    log_msg("[-] Could not verify real page content after retries.")
    return False


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
    """Locate a Chromium-based browser executable on Windows."""
    candidates = _BROWSER_PATHS.get(browser, [])
    for path in candidates:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError(
        f"{browser.title()} not found. Install it or set BROWSER_PATH env var."
    )


def _is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a TCP port is accepting connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0


async def test_search(
    browser_name: str = "chrome",
    target_url: str = "https://example.com/",
) -> None:
    # --- Locate browser ---
    browser_path = os.environ.get("BROWSER_PATH") or _find_browser(browser_name)
    log_msg(f"[*] Using {browser_name.title()}: {browser_path}")

    # --- Temp profile dir (clean, no cached sessions) ---
    temp_profile = tempfile.mkdtemp(prefix="target_bypass_")
    debug_port = 9222
    url = target_url

    # --- Launch browser as a GENUINE process ---
    # No Playwright, no CDP injection, no --enable-automation.
    # Browser starts completely clean — CF Turnstile and PX see a real browser.
    launch_args = [
        browser_path,
        f"--remote-debugging-port={debug_port}",
        f"--user-data-dir={temp_profile}",
        "--incognito",
        "--start-maximized",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
        url,  # Navigate directly — page loads before any CDP connection
    ]

    log_msg(
        f"[*] Launching {browser_name.title()} with --remote-debugging-port={debug_port}"
    )
    browser_proc = subprocess.Popen(
        launch_args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        # --- Wait for Chrome to be ready ---
        log_msg("[*] Waiting for Chrome debug port...")
        for _ in range(30):
            if _is_port_open(debug_port):
                break
            await asyncio.sleep(0.5)
        else:
            log_msg("[-] Browser debug port never opened. Aborting.")
            browser_proc.kill()
            return

        # Give Chrome extra time to load the initial URL and start
        # processing any CF/PX challenges BEFORE we connect.
        # This is the key: challenges see a genuine browser, not CDP.
        log_msg("[*] Waiting 8s for initial page load + challenge processing...")
        await asyncio.sleep(8)

        # Chrome already loaded the URL as a genuine browser.
        # We connect now ONLY to observe page state and coordinate pyautogui.
        # No stealth JS needed — Chrome IS genuine.
        log_msg("[*] Connecting Playwright via connect_over_cdp...")
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(
                f"http://localhost:{debug_port}"
            )

            # Get the existing page (Chrome already navigated)
            contexts = browser.contexts
            if not contexts:
                log_msg("[-] No browser contexts found.")
                return

            # Apply stealth JS before any further navigations/redirects expose webdriver=true
            STEALTH_JS = """
            (() => {
                try { delete Object.getPrototypeOf(navigator).webdriver; } catch(e) {}
                try { Object.defineProperty(navigator, 'webdriver', {get: () => undefined}); } catch(e) {}
                try { Object.defineProperty(navigator, 'languages', {get: () => Object.freeze(['en-US', 'en'])}); } catch(e) {}
                try { Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0}); } catch(e) {}
                try {
                    const origQuery = navigator.permissions.query.bind(navigator.permissions);
                    Object.defineProperty(navigator.permissions, 'query', {
                        value: (desc) => {
                            if (desc && desc.name === 'notifications') return Promise.resolve({ state: Notification.permission || 'default' });
                            return origQuery(desc);
                        }
                    });
                } catch(e) {}
            })();
            """
            for ctx in contexts:
                await ctx.add_init_script(STEALTH_JS)

            pages = contexts[0].pages
            page = pages[0] if pages else await contexts[0].new_page()

            # Log current state
            title = await page.title()
            current_url = page.url
            webdriver_state = await page.evaluate("navigator.webdriver")
            log_msg(
                f"[*] Connected! Title: '{title}' URL: {current_url} | webdriver={webdriver_state}"
            )

            # Move browser window to (0, 0) for deterministic coordinate mapping
            try:
                await page.evaluate("window.moveTo(0, 0)")
                await asyncio.sleep(0.3)
            except Exception:
                pass

            # Network logging
            def _net_log(msg):
                with open("debug_px.txt", "a", encoding="utf-8") as f:
                    f.write(msg + "\n")

            async def _log_response(r):
                if "bizographics" in r.url or "google" in r.url:
                    return
                msg = f"[RES] {r.status} {r.url}"
                if any(
                    k in r.url
                    for k in ("/collector", "px/", "/xhr", "captcha", "bundle")
                ):
                    try:
                        headers = await r.all_headers()
                        set_cookies = headers.get("set-cookie", "")
                        if set_cookies:
                            msg += f"\n   Set-Cookie: {set_cookies}"
                    except Exception:
                        pass
                    try:
                        text = await r.text()
                        msg += f"\n   BODY: {text[:500]}"
                    except Exception:
                        msg += "\n   BODY: <could not read>"
                _net_log(msg)

            page.on(
                "request",
                lambda r: (
                    _net_log(f"[REQ] {r.method} {r.url}")
                    if not any(d in r.url for d in _TRACKER_DOMAINS)
                    else None
                ),
            )
            page.on(
                "response",
                lambda r: asyncio.create_task(_log_response(r)),
            )

            # --- Solve challenges ---
            log_msg(f"[*] Starting challenge solving on {url}")
            success = await solve_challenges(page, url)

            # Final status report
            title = await page.title()
            final_url = page.url
            log_msg(f"Title : {title}")
            log_msg(f"URL   : {final_url}")

            try:
                await page.screenshot(path="target_debug.png")
            except Exception:
                pass

            if success:
                log_msg("[+] \u2705 Bypass SUCCESSFUL \u2014 real page loaded!")
            else:
                log_msg("[-] \u274c Failed to bypass target site.")

            await asyncio.sleep(5)

    finally:
        # Clean up browser process and temp profile
        try:
            browser_proc.terminate()
            browser_proc.wait(timeout=5)
        except Exception:
            browser_proc.kill()
        shutil.rmtree(temp_profile, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Target-site stealth bypass via subprocess Chrome/Edge + PyAutoGUI."
    )
    parser.add_argument(
        "--browser",
        choices=["chrome", "edge"],
        default="chrome",
        help="Browser to use (default: chrome). Both Chrome and Edge are Chromium-based.",
    )
    parser.add_argument(
        "--url",
        default="https://example.com/",
        help="Target URL for challenge diagnostics.",
    )
    args = parser.parse_args()
    asyncio.run(test_search(browser_name=args.browser, target_url=args.url))


if __name__ == "__main__":
    main()
