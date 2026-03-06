# ./src/web_scraper_toolkit/browser/px_solver.py
"""
PerimeterX Challenge Solver
============================

Handles PerimeterX "Press & Hold" and related CAPTCHA challenges using
OS-level mouse events via pyautogui (Win32 SendInput).

Run: Not standalone  -- imported by playwright_handler.py during fetch_page_content().
Inputs: A Playwright Page object with a visible PerimeterX challenge.
Outputs: bool indicating whether the challenge was solved.
Notes:
  - pyautogui is an OPTIONAL dependency. Solver gracefully returns False if unavailable.
  - Must run in HEADED mode (real browser window visible on a display).
  - Will briefly control the user's real cursor during the hold.
  - pyautogui.FAILSAFE = True  -- move mouse to any screen corner to abort.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Dict, Optional, Tuple

from playwright.async_api import Page

from ._px_solver import perform_os_hold as _perform_os_hold_impl

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy pyautogui import  -- doesn't crash if package is missing
# ---------------------------------------------------------------------------

_pyautogui: Optional[Any] = None
_pyautogui_available: Optional[bool] = None


def _ensure_pyautogui() -> bool:
    """Attempt to import pyautogui lazily. Returns True if available."""
    global _pyautogui, _pyautogui_available
    if _pyautogui_available is not None:
        return _pyautogui_available
    try:
        # Force per-monitor DPI awareness so pyautogui uses physical pixels
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

        import pyautogui as _pag

        _pag.FAILSAFE = True
        _pag.PAUSE = 0
        _pyautogui = _pag
        _pyautogui_available = True
    except ImportError:
        _pyautogui_available = False
        logger.debug("pyautogui not installed  -- PX solver unavailable.")
    except Exception as exc:
        # E.g. no display on headless Linux
        _pyautogui_available = False
        logger.debug("pyautogui init failed (%s)  -- PX solver unavailable.", exc)
    return _pyautogui_available


# ---------------------------------------------------------------------------
# Screen coordinate helpers
# ---------------------------------------------------------------------------


async def _get_browser_chrome_offset(page: Page) -> Dict[str, float]:
    """Return browser window position, chrome height, and device pixel ratio."""
    return await page.evaluate(
        """() => ({
        screenX:  window.screenX,
        screenY:  window.screenY,
        chromeH:  window.outerHeight - window.innerHeight,
        dpr:      window.devicePixelRatio || 1
    })"""
    )


def _viewport_to_screen(
    win_info: Dict[str, float], vp_x: float, vp_y: float
) -> Tuple[float, float]:
    """Translate viewport-relative (CSS) coords to absolute physical screen coords.

    Multiplies by devicePixelRatio so pyautogui (which operates in physical
    device pixels after SetProcessDpiAwareness) targets the correct position.
    """
    dpr = win_info.get("dpr", 1)
    return (
        (win_info["screenX"] + vp_x) * dpr,
        (win_info["screenY"] + win_info["chromeH"] + vp_y) * dpr,
    )


def _os_mouse_move(sx: float, sy: float, duration: float = 0.6) -> None:
    """Move the real OS cursor with human-like easing."""
    assert _pyautogui is not None
    _pyautogui.moveTo(
        int(sx),
        int(sy),
        duration=duration,
        tween=_pyautogui.easeOutQuad,
    )


def _get_active_window_rect() -> Optional[Tuple[int, int, int, int, str]]:
    """Return active window bounds as (left, top, right, bottom, title)."""
    if not _ensure_pyautogui() or _pyautogui is None:
        return None
    getter = getattr(_pyautogui, "getActiveWindow", None)
    if getter is None:
        return None
    try:
        window = getter()
    except Exception:
        return None
    if window is None:
        return None
    try:
        left = int(getattr(window, "left"))
        top = int(getattr(window, "top"))
        width = int(getattr(window, "width"))
        height = int(getattr(window, "height"))
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    right = left + width
    bottom = top + height
    title = str(getattr(window, "title", "") or "")
    return (left, top, right, bottom, title)


def _active_window_contains_point(sx: float, sy: float) -> bool:
    rect = _get_active_window_rect()
    if rect is None:
        return False
    left, top, right, bottom, _title = rect
    return left <= int(sx) <= right and top <= int(sy) <= bottom


# ---------------------------------------------------------------------------
# Public Solver API
# ---------------------------------------------------------------------------


class PerimeterXSolver:
    """
    OS-level solver for PerimeterX challenges.

    Uses pyautogui to generate real Win32 SendInput mouse events that
    are indistinguishable from physical hardware, bypassing CDP behavioral
    fingerprinting.
    """

    @staticmethod
    def is_available() -> bool:
        """Check if pyautogui is importable and a display is available."""
        return _ensure_pyautogui()

    @staticmethod
    async def warn_before_os_input_takeover(
        *,
        countdown_seconds: int = 3,
        reason: str = "anti-bot challenge solve",
    ) -> None:
        """
        Emit a user-visible warning before OS-level mouse input starts.

        This warning gives operators a short window to focus the correct browser
        window and avoid accidental interaction with unrelated applications.
        """
        seconds = max(0, min(15, int(countdown_seconds)))
        logger.warning(
            "PX Solver: OS mouse control will begin for %s. "
            "Bring the target browser window to foreground now.",
            reason,
        )
        if seconds <= 0:
            return
        for remaining in range(seconds, 0, -1):
            logger.warning(
                "PX Solver: OS input takeover starts in %ss (move cursor to a screen corner to abort).",
                remaining,
            )
            await asyncio.sleep(1)

    @staticmethod
    async def ensure_safe_active_window(page: Page) -> bool:
        """
        Verify browser window focus/foreground before OS-level input.

        Safety rules:
          1. Target page must be brought to front and have DOM focus.
          2. OS active window must be discoverable.
          3. Target browser window coordinates must fall inside the active window.
        """
        if not _ensure_pyautogui():
            return False

        try:
            await page.bring_to_front()
        except Exception:
            pass
        await asyncio.sleep(0.2)

        try:
            has_focus = bool(await page.evaluate("document.hasFocus()"))
        except Exception:
            has_focus = False
        if not has_focus:
            logger.warning("PX Solver: Browser tab is not focused; aborting OS input.")
            return False

        rect = _get_active_window_rect()
        if rect is None:
            logger.warning(
                "PX Solver: Active window could not be verified; aborting OS input."
            )
            return False
        left, top, right, bottom, title = rect

        try:
            win = await _get_browser_chrome_offset(page)
        except Exception:
            logger.warning(
                "PX Solver: Could not read browser window coordinates; aborting OS input."
            )
            return False

        screen_x = float(win.get("screenX", 0.0))
        screen_y = float(win.get("screenY", 0.0))
        dpr = float(win.get("dpr", 1.0) or 1.0)
        # Some environments expose CSS-px screen coordinates; others align
        # with physical px. Accept either to prevent false negatives.
        candidate_points = [
            (screen_x, screen_y),
            (screen_x * dpr, screen_y * dpr),
        ]
        inside_active = any(
            left <= int(px) <= right and top <= int(py) <= bottom
            for px, py in candidate_points
        )
        if not inside_active:
            logger.warning(
                "PX Solver: Browser window is not foreground active window "
                "(active='%s' bounds=%s,%s,%s,%s).",
                title,
                left,
                top,
                right,
                bottom,
            )
            return False

        return True

    @staticmethod
    async def solve_press_and_hold(page: Page) -> bool:
        """
        Solve a PerimeterX "Press & Hold" challenge.

        Scans all frames for the challenge button, performs an OS-level
        mouse hold, and polls the DOM for the checkmark/completion state.
        Handles multiple rounds (the challenge may cycle 2-4 times).

        Returns True if the challenge was solved.
        """
        if not _ensure_pyautogui():
            logger.warning(
                "PX Solver: pyautogui unavailable  -- cannot solve Press & Hold."
            )
            return False

        logger.info("PX Solver: Scanning for Press & Hold challenge...")

        # The PX challenge can require multiple rounds. After one successful
        # hold, the button may re-appear. We loop up to 8 rounds.
        solved_any_round = False

        for round_num in range(1, 9):
            # Poll up to 15s for the button to appear in any frame.
            # Use smallest-bbox strategy to target the actual clickable button
            # (typically ~253x50) rather than the container (#px-captcha ~530x100).
            hold_element = None
            for _tick in range(30):
                candidates = []
                for frame in page.frames:
                    # Strategy 1: Inner button inside #px-captcha
                    try:
                        inner_btn = frame.locator("#px-captcha button")
                        if (
                            await inner_btn.count() > 0
                            and await inner_btn.first.is_visible()
                        ):
                            box = await inner_btn.first.bounding_box()
                            if box and box["y"] < 2000:
                                candidates.append(
                                    (inner_btn, box["width"] * box["height"])
                                )
                    except Exception:
                        pass

                    # Strategy 2: ARIA button
                    try:
                        loc = frame.get_by_role("button", name="Press & Hold")
                        if await loc.count() > 0 and await loc.first.is_visible():
                            box = await loc.first.bounding_box()
                            if box and box["y"] < 2000:
                                candidates.append((loc, box["width"] * box["height"]))
                    except Exception:
                        pass

                    # Strategy 3: #px-captcha container (fallback)
                    try:
                        loc2 = frame.locator("#px-captcha")
                        if await loc2.count() > 0 and await loc2.first.is_visible():
                            box = await loc2.first.bounding_box()
                            if box and box["y"] < 2000:
                                candidates.append((loc2, box["width"] * box["height"]))
                    except Exception:
                        pass

                if candidates:
                    # Pick the smallest bounding box — that's the real button
                    candidates.sort(key=lambda c: c[1])
                    hold_element = candidates[0][0]
                    break
                await asyncio.sleep(0.5)

            if not hold_element:
                if solved_any_round:
                    logger.info(
                        "PX Solver: No button found after round %d -- challenge cleared.",
                        round_num - 1,
                    )
                else:
                    logger.info("PX Solver: No Press & Hold button found after 15s.")
                break

            logger.info(
                "PX Solver: Round %d -- found PX challenge element. Engaging OS mouse.",
                round_num,
            )
            result = await _perform_os_hold(page, hold_element)
            if result:
                solved_any_round = True
                logger.info("PX Solver: Round %d passed! Reloading page...", round_num)

                # Reload the page after a successful hold. PX sets a clearance
                # cookie on success, and reloading should serve the real page
                # instead of re-presenting the challenge in an infinite loop.
                try:
                    await page.reload(wait_until="domcontentloaded", timeout=15000)
                except Exception as reload_exc:
                    logger.debug("PX Solver: Reload error (may be OK): %s", reload_exc)
                await asyncio.sleep(2.0)

                # Check if challenge is still present after reload
                try:
                    content = (await page.content()).lower()
                except Exception:
                    # Page navigated away -- success
                    logger.info("PX Solver: Page detached after reload -- success.")
                    break

                if not any(m in content for m in ("px-captcha", "press & hold")):
                    logger.info("PX Solver: Challenge cleared after reload!")
                    break
                else:
                    logger.info(
                        "PX Solver: Challenge still present after reload, retrying..."
                    )
            else:
                logger.warning(
                    "PX Solver: Round %d hold failed, retrying...", round_num
                )
                await asyncio.sleep(2.0)

        return solved_any_round

    @staticmethod
    async def solve_cloudflare_checkbox(page: Page) -> bool:
        """
        Click a Cloudflare Turnstile checkbox using real OS mouse.

        Returns True if the checkbox was found and clicked.
        """
        if not _ensure_pyautogui():
            return False
        if not await PerimeterXSolver.ensure_safe_active_window(page):
            return False

        for frame in page.frames:
            cb = frame.locator(".ctp-checkbox-label")
            try:
                if await cb.count() == 0 or not await cb.first.is_visible():
                    continue
            except Exception:
                continue

            box = await cb.first.bounding_box()
            if not box:
                continue

            win = await _get_browser_chrome_offset(page)
            cx = box["x"] + box["width"] / 2 + random.uniform(-3, 3)
            cy = box["y"] + box["height"] / 2 + random.uniform(-2, 2)
            sx, sy = _viewport_to_screen(win, cx, cy)
            if not _active_window_contains_point(sx, sy):
                logger.warning(
                    "PX Solver: Refusing OS click outside active window bounds."
                )
                return False

            logger.info("PX Solver: OS-clicking CF checkbox at (%d, %d)", sx, sy)
            _os_mouse_move(sx, sy, duration=random.uniform(0.3, 0.6))
            assert _pyautogui is not None
            _pyautogui.click()
            return True

        return False


# ---------------------------------------------------------------------------
# Internal hold implementation
# ---------------------------------------------------------------------------


async def _perform_os_hold(page: Page, hold_element: Any) -> bool:
    """
    Execute the OS-level press-and-hold on the PX challenge element.

    Delegates to the private helper module while preserving access to
    legacy module globals required by existing tests/patches.
    """
    return await _perform_os_hold_impl(
        page=page,
        hold_element=hold_element,
        ensure_safe_active_window=PerimeterXSolver.ensure_safe_active_window,
        get_browser_chrome_offset=_get_browser_chrome_offset,
        viewport_to_screen=_viewport_to_screen,
        active_window_contains_point=_active_window_contains_point,
        os_mouse_move=_os_mouse_move,
        pyautogui_getter=lambda: _pyautogui,
        logger=logger,
        random_module=random,
        asyncio_module=asyncio,
    )
