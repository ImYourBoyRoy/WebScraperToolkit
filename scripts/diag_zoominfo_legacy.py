import asyncio
import os
import random
import subprocess
import time
import tempfile
import shutil
import pyautogui
from playwright.async_api import async_playwright

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


async def _get_browser_chrome_offset(page):
    return await page.evaluate("""() => ({
        screenX: window.screenX,
        screenY: window.screenY,
        outerH: window.outerHeight,
        innerH: window.innerHeight,
        chromeH: window.outerHeight - window.innerHeight,
        dpr: window.devicePixelRatio || 1
    })""")


def _viewport_to_screen(win_info, vp_x, vp_y):
    dpr = float(win_info.get("dpr", 1.0))
    return (
        (float(win_info["screenX"]) + vp_x) * dpr,
        (float(win_info["screenY"]) + float(win_info["chromeH"]) + vp_y) * dpr,
    )


def _os_mouse_move(target_x, target_y, duration=0.65):
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


async def attempt_os_hold(page):
    candidates = []
    for frame in page.frames:
        try:
            btn = frame.get_by_role("button", name="Press & Hold")
            if await btn.count() > 0 and await btn.first.is_visible():
                box = await btn.first.bounding_box()
                if box:
                    candidates.append((btn, box))
        except Exception:
            pass

        try:
            inner = frame.locator("#px-captcha button")
            if await inner.count() > 0 and await inner.first.is_visible():
                box = await inner.first.bounding_box()
                if box:
                    candidates.append((inner, box))
        except Exception:
            pass

        try:
            container = frame.locator("#px-captcha")
            if await container.count() > 0 and await container.first.is_visible():
                box = await container.first.bounding_box()
                if box:
                    candidates.append((container, box))
        except Exception:
            pass

    if not candidates:
        print("[-] Could not find hold button.")
        return False

    candidates.sort(key=lambda c: c[1]["width"] * c[1]["height"])
    btn, box = candidates[0]

    await page.bring_to_front()
    await asyncio.sleep(0.3)
    win = await _get_browser_chrome_offset(page)
    x = box["x"] + box["width"] / 2
    y = box["y"] + box["height"] / 2
    sx, sy = _viewport_to_screen(win, x, y)

    print(f"[*] Moving OS mouse exactly to {sx}, {sy} ...")
    _os_mouse_move(sx, sy, duration=0.65)
    await asyncio.sleep(0.1)

    print("[*] OS mouseDown ... holding")
    pyautogui.mouseDown()
    started = time.monotonic()
    success = False

    while time.monotonic() - started < 12.0:
        await asyncio.sleep(0.25)
        # Check completion
        try:
            seen = False
            for f in page.frames:
                done = f.get_by_role("button", name="Human Challenge completed")
                if await done.count() > 0:
                    seen = True
            if seen:
                print(
                    f"[*] Completion marker seen at {time.monotonic() - started:.1f}s!"
                )
                success = True
                break
        except Exception:
            pass

    pyautogui.mouseUp()
    print("[*] OS mouseUp.")
    await asyncio.sleep(0.9)
    return success


async def main():
    url = "https://www.zoominfo.com/c/amco-ranger/5000168"
    chrome_path = os.path.expandvars(
        r"%LocalAppData%\Google\Chrome\Application\chrome.exe"
    )
    prof = tempfile.mkdtemp(prefix="zi_test_")
    port = 9227

    proc = subprocess.Popen(
        [
            chrome_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={prof}",
            "--start-maximized",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        print("[*] Waiting 8s for challenge loading...")
        await asyncio.sleep(8)

        async with async_playwright() as p:
            print("[*] Connecting CDP...")
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
            ctx = browser.contexts[0]
            if not ctx.pages:
                page = await ctx.new_page()
            else:
                page = ctx.pages[0]

            print("[*] Adding stealth script...")
            await ctx.add_init_script(LEGACY_STEALTH_JS)

            print(f"[*] Pre-hold title: {await page.title()}")
            content = await page.content()
            if "px-captcha" in content.lower():
                print("[*] Challenge is present. Attempting hold...")
                await attempt_os_hold(page)
                print("[*] Settling 5s for clearance flow...")
                await asyncio.sleep(5.0)

            print("[*] Initiating page.goto revisit ...")
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            status = resp.status if resp else None

            await asyncio.sleep(3)
            final_title = await page.title()
            print(f"[*] Final status: {status}")
            print(f"[*] Final title: {final_title}")

            content = await page.content()
            if "company-name" in content:
                print("[+] SUCCESS! Real page loaded.")
            else:
                print("[-] FAILED. Blocked or challenge looping.")
    finally:
        proc.kill()
        shutil.rmtree(prof, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
