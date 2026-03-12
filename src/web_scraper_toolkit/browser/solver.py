# ./src/web_scraper_toolkit/browser/solver.py
"""
Cloudflare Spatial Solver
=========================

Unified dynamic solver for Cloudflare challenges with shadow DOM introspection.

Uses a monkey-patched attachShadow (injected via context.add_init_script in
page_ops.py) to capture the closed shadow root reference.  This lets us use
frame.evaluate() to read the actual widget state:
  - #verifying display → spinner still running
  - label.cb-lb visible → checkbox is clickable

The solver runs a single polling loop that checks title, frame, and widget
state every tick and clicks as soon as the checkbox is confirmed ready.

Run: imported by page_ops.py during fetch_page_content.
Inputs: a Playwright Page object on a Cloudflare challenge.
Outputs: bool indicating whether the challenge was solved.
Side effects: mouse clicks, possible page navigations.
Operational notes: requires the shadow DOM capture init script in page_ops.py.
  Falls back to time-based settle if the capture didn't work.
"""

import logging
import random
import time
from typing import Optional
from playwright.async_api import Frame, Page

logger = logging.getLogger(__name__)

_CHALLENGE_TITLES = ("just a moment", "attention required", "403")

# Checkbox center offset within the 300x65 Turnstile iframe.
_CHECKBOX_X_OFFSET = 28
_CHECKBOX_Y_RATIO = 0.5

# Maximum time for the entire solver loop (seconds).
_SOLVER_TOTAL_TIMEOUT = 30

# Fallback settle time if shadow DOM capture didn't work.
_FALLBACK_SETTLE_SECONDS = 5


def _log(msg: str) -> None:
    """Log to both logger and stdout so the user sees solver actions."""
    logger.info(msg)
    print(f"  [Solver] {msg}", flush=True)


# JavaScript snippets evaluated inside the Turnstile frame via frame.evaluate().
# They use the __capturedShadow reference set by the init script in page_ops.py.

_JS_WIDGET_STATE = """
() => {
    const shadow = document.body && document.body.__capturedShadow;
    if (!shadow) return { captured: false };

    const verifying = shadow.querySelector('#verifying');
    const checkbox = shadow.querySelector("label.cb-lb input[type='checkbox']");
    const successEl = shadow.querySelector('#success');
    const cbLabel = shadow.querySelector('.cb-lb-t');

    return {
        captured: true,
        verifyingVisible: verifying ? verifying.style.display !== 'none' : false,
        checkboxPresent: !!checkbox,
        successVisible: successEl ? successEl.style.display !== 'none' : false,
        labelText: cbLabel ? cbLabel.textContent : null,
    };
}
"""


class CloudflareSolver:
    """
    Dynamic Cloudflare solver with shadow DOM introspection.
    Uses a single unified polling loop with real widget state detection.
    """

    @staticmethod
    async def _is_challenge_title(page: Page) -> bool:
        """Check if the current page title indicates an active challenge."""
        try:
            title = (await page.title()).lower()
            return any(marker in title for marker in _CHALLENGE_TITLES)
        except Exception:
            return True

    @staticmethod
    async def _find_turnstile_frame(page: Page) -> Optional[Frame]:
        """Find the Turnstile cross-origin frame via CDP-level page.frames."""
        for frame in page.frames:
            url = frame.url.lower()
            if "challenges.cloudflare.com" in url and "turnstile" in url:
                return frame
        return None

    @staticmethod
    async def _get_iframe_bbox(page: Page, frame: Frame) -> Optional[dict]:
        """Get iframe bounding box via frame.frame_element() (bypasses shadow DOM)."""
        try:
            iframe_element = await frame.frame_element()
            bbox = await iframe_element.bounding_box()
            if bbox:
                return bbox
        except Exception as e:
            _log(f"frame.frame_element() failed: {e}")

        # Fallback: light-DOM container patterns
        try:
            for selector in [
                "div[style*='display: grid']",
                "div[id*='cf-chl']",
                "[id^='cf-chl-widget']",
            ]:
                el = page.locator(selector).first
                if await el.count() > 0:
                    bbox = await el.bounding_box()
                    if bbox and bbox["width"] > 0:
                        return bbox
        except Exception:
            pass
        return None

    @staticmethod
    async def _get_widget_state(frame: Frame) -> dict:
        """
        Query the Turnstile widget state through the captured shadow root.
        Returns a dict with: captured, verifyingVisible, checkboxPresent,
        successVisible, labelText.
        """
        try:
            return await frame.evaluate(_JS_WIDGET_STATE)
        except Exception:
            return {"captured": False}

    @staticmethod
    async def _click_at_checkbox_coordinates(page: Page, bbox: dict) -> bool:
        """Click at the checkbox position with human-like mouse movement."""
        click_x = bbox["x"] + _CHECKBOX_X_OFFSET + random.uniform(-3, 3)
        click_y = (
            bbox["y"] + (bbox["height"] * _CHECKBOX_Y_RATIO) + random.uniform(-3, 3)
        )

        _log(f"Clicking at ({click_x:.0f}, {click_y:.0f})")

        try:
            start_x = click_x + random.randint(-60, 60)
            start_y = click_y + random.randint(-30, 30)
            await page.mouse.move(start_x, start_y)
            await page.wait_for_timeout(random.randint(80, 200))

            await page.mouse.move(click_x, click_y, steps=random.randint(8, 15))
            await page.wait_for_timeout(random.randint(40, 150))

            await page.mouse.down()
            await page.wait_for_timeout(random.randint(50, 150))
            await page.mouse.up()

            _log("Click delivered.")
            return True
        except Exception as e:
            _log(f"Coordinate click failed: {e}")
            return False

    @staticmethod
    async def _click_checkbox_via_locator(page: Page, frame: Frame) -> bool:
        """Click checkbox using Playwright locators (open shadow DOM path)."""
        for name, selector in [
            ("input", "label.cb-lb input[type='checkbox']"),
            (".cb-i", ".cb-i"),
            ("label", "label.cb-lb"),
        ]:
            try:
                el = frame.locator(selector)
                if await el.count() > 0:
                    _log(f"Clicking via locator: {name}")
                    await el.first.click(timeout=5000)
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    async def _try_text_offset_click(page: Page) -> bool:
        """Legacy fallback: click left of 'Verify you are human' text."""
        for frame in page.frames:
            try:
                for text in ("Verify you are human", "Verifying you are human"):
                    label = frame.get_by_text(text)
                    if await label.count() > 0:
                        box = await label.bounding_box()
                        if box:
                            tx = box["x"] - 20
                            ty = box["y"] + box["height"] / 2
                            _log(f"Text offset click at ({int(tx)}, {int(ty)})")
                            await page.mouse.move(tx, ty, steps=10)
                            await page.wait_for_timeout(random.randint(200, 400))
                            await page.mouse.down()
                            await page.wait_for_timeout(random.randint(100, 250))
                            await page.mouse.up()
                            return True
            except Exception:
                continue
        return False

    @staticmethod
    async def _wait_for_challenge_resolution(page: Page, max_seconds: int = 15) -> bool:
        """Wait for the page to leave the challenge state after a click."""
        for tick in range(max_seconds):
            await page.wait_for_timeout(1000)
            if not await CloudflareSolver._is_challenge_title(page):
                _log(f"Challenge resolved {tick + 1}s after click!")
                return True
        return False

    @staticmethod
    async def solve_spatial(page: Page) -> bool:
        """
        Unified dynamic solver for Cloudflare Turnstile challenges.

        Single polling loop checks all conditions every ~1s:
        - Title change → auto-solve detected
        - Frame presence → iframe discovered
        - Widget state → verifying done, checkbox ready
        - Click → as soon as checkbox is confirmed visible

        Shadow DOM introspection uses the captured shadow root reference
        (injected via init script in page_ops.py). Falls back to time-based
        settle if the capture didn't work.
        """
        try:
            _log("─── Solver invoked ───")

            frame: Optional[Frame] = None
            bbox: Optional[dict] = None
            frame_found_at: Optional[float] = None
            shadow_captured = False
            click_count = 0

            start_time = time.monotonic()

            for tick in range(_SOLVER_TOTAL_TIMEOUT):
                elapsed = time.monotonic() - start_time

                # ── Check 1: Has the challenge auto-resolved? ──
                if not await CloudflareSolver._is_challenge_title(page):
                    _log(f"Auto-solve succeeded after {elapsed:.0f}s (title changed).")
                    return True

                # ── Check 2: Is the Turnstile frame present? ──
                if frame is None:
                    frame = await CloudflareSolver._find_turnstile_frame(page)
                    if frame:
                        frame_found_at = time.monotonic()
                        _log(f"[{elapsed:.0f}s] Turnstile frame found.")
                        bbox = await CloudflareSolver._get_iframe_bbox(page, frame)
                        if bbox:
                            _log(
                                f"  Iframe bbox: x={bbox['x']:.0f}, y={bbox['y']:.0f}, "
                                f"w={bbox['width']:.0f}, h={bbox['height']:.0f}"
                            )
                    elif tick > 0 and tick % 5 == 0:
                        _log(f"[{elapsed:.0f}s] Waiting for Turnstile frame...")
                    await page.wait_for_timeout(1000)
                    continue  # Don't try to click on the same tick we found the frame

                # ── Check 3: Is the widget ready for clicking? ──
                state = await CloudflareSolver._get_widget_state(frame)

                if state.get("captured"):
                    shadow_captured = True

                    if state.get("successVisible"):
                        _log(f"[{elapsed:.0f}s] Widget shows Success!")
                        # Wait for redirect
                        if await CloudflareSolver._wait_for_challenge_resolution(page):
                            return True
                        if not await CloudflareSolver._is_challenge_title(page):
                            return True
                        _log("Success shown but page didn't redirect. Continuing...")
                        await page.wait_for_timeout(1000)
                        continue

                    if state.get("verifyingVisible"):
                        _log(f"[{elapsed:.0f}s] Widget verifying... (waiting)")
                        await page.wait_for_timeout(1000)
                        continue

                    if state.get("checkboxPresent"):
                        label = state.get("labelText", "")
                        _log(f"[{elapsed:.0f}s] Checkbox ready! ('{label}')")

                        # Try locator click first, then coordinate click
                        clicked = await CloudflareSolver._click_checkbox_via_locator(
                            page, frame
                        )
                        if not clicked and bbox:
                            clicked = (
                                await CloudflareSolver._click_at_checkbox_coordinates(
                                    page, bbox
                                )
                            )

                        if clicked:
                            click_count += 1
                            if await CloudflareSolver._wait_for_challenge_resolution(
                                page
                            ):
                                return True
                            if not await CloudflareSolver._is_challenge_title(page):
                                return True
                            _log(f"Click #{click_count} didn't resolve. Resetting...")
                            frame = None
                            bbox = None
                            frame_found_at = None
                        await page.wait_for_timeout(1000)
                        continue

                    # Shadow captured but no checkbox, no verifying, no success
                    # Widget might be in transition or expired
                    _log(
                        f"[{elapsed:.0f}s] Widget in unknown state (captured). Waiting..."
                    )
                    await page.wait_for_timeout(1000)
                    continue

                # ── Fallback: Shadow DOM not captured — use time-based settle ──
                if not shadow_captured and frame_found_at is not None:
                    settle_elapsed = time.monotonic() - frame_found_at
                    remaining = _FALLBACK_SETTLE_SECONDS - settle_elapsed

                    if remaining > 0:
                        if tick % 3 == 0:
                            _log(
                                f"[{elapsed:.0f}s] No shadow capture — settle {remaining:.0f}s"
                            )
                        await page.wait_for_timeout(1000)
                        continue

                    # Settle done — click at coordinates
                    if bbox:
                        _log(
                            f"[{elapsed:.0f}s] Settle done — clicking (no shadow capture)..."
                        )
                        clicked = await CloudflareSolver._click_at_checkbox_coordinates(
                            page, bbox
                        )
                        if clicked:
                            click_count += 1
                            if await CloudflareSolver._wait_for_challenge_resolution(
                                page
                            ):
                                return True
                            if not await CloudflareSolver._is_challenge_title(page):
                                return True
                            _log(f"Click #{click_count} didn't resolve. Resetting...")
                            frame = None
                            bbox = None
                            frame_found_at = None

                await page.wait_for_timeout(1000)

            # ── Timeout: try text offset as last resort ──
            _log("Solver loop exhausted. Trying text offset fallback...")
            if await CloudflareSolver._try_text_offset_click(page):
                if await CloudflareSolver._wait_for_challenge_resolution(page):
                    return True

            _log("─── Solver FAILED ───")
            return False

        except Exception as e:
            _log(f"Solver error: {e}")
            return False
