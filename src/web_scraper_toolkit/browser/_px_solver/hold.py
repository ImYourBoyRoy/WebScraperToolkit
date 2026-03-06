# ./src/web_scraper_toolkit/browser/_px_solver/hold.py
"""
Internal OS hold routine for PerimeterX "Press & Hold" verification flows.
Run: imported by browser.px_solver; not a standalone command.
Inputs: page/element targets plus dependency callables for mouse/window checks.
Outputs: bool indicating whether hold interaction likely cleared the challenge.
Side effects: performs OS cursor movement, mouse down/up, and DOM polling loops.
Operational notes: dependency injection keeps legacy module globals patch-compatible.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable


async def perform_os_hold(
    *,
    page: Any,
    hold_element: Any,
    ensure_safe_active_window: Callable[[Any], Awaitable[bool]],
    get_browser_chrome_offset: Callable[[Any], Awaitable[dict[str, float]]],
    viewport_to_screen: Callable[[dict[str, float], float, float], tuple[float, float]],
    active_window_contains_point: Callable[[float, float], bool],
    os_mouse_move: Callable[[float, float, float], None],
    pyautogui_getter: Callable[[], Any],
    logger: Any,
    random_module: Any,
    asyncio_module: Any,
) -> bool:
    """
    Execute the OS-level press-and-hold on the PX challenge element.

    Holds the mouse and dynamically polls for the 'Human Challenge completed'
    button or disappearance of px-captcha markers. Releases as soon as
    completion is detected, or after a 15s safety timeout.
    """
    try:
        await page.bring_to_front()
    except Exception:
        pass
    await asyncio_module.sleep(0.3)

    if not await ensure_safe_active_window(page):
        logger.warning(
            "PX Solver: Safety pre-check failed (window not active/foreground)."
        )
        return False

    box = await hold_element.first.bounding_box()
    if not box:
        logger.warning("PX Solver: Could not get bounding box.")
        return False

    logger.info(
        "PX Solver: bbox x=%.0f y=%.0f w=%.0f h=%.0f",
        box["x"],
        box["y"],
        box["width"],
        box["height"],
    )

    win = await get_browser_chrome_offset(page)
    logger.info(
        "PX Solver: window screenX=%.0f screenY=%.0f chromeH=%.0f",
        win["screenX"],
        win["screenY"],
        win["chromeH"],
    )

    target_vx = box["x"] + box["width"] / 2
    target_vy = box["y"] + box["height"] / 2
    target_sx, target_sy = viewport_to_screen(win, target_vx, target_vy)
    if not active_window_contains_point(target_sx, target_sy):
        logger.warning(
            "PX Solver: Target point is outside active window bounds; aborting hold."
        )
        return False

    pyautogui = pyautogui_getter()
    if pyautogui is None:
        logger.warning("PX Solver: pyautogui handle missing during hold.")
        return False

    start_sx = target_sx + random_module.randint(-200, -50)
    start_sy = target_sy + random_module.randint(-100, 100)
    pyautogui.moveTo(int(start_sx), int(start_sy), duration=0.1)
    await asyncio_module.sleep(random_module.uniform(0.15, 0.35))

    mid_x = start_sx + (target_sx - start_sx) * 0.3 + random_module.randint(-20, 20)
    mid_y = start_sy + (target_sy - start_sy) * 0.3 + random_module.randint(-10, 10)
    pyautogui.moveTo(int(mid_x), int(mid_y), duration=random_module.uniform(0.1, 0.2))
    await asyncio_module.sleep(random_module.uniform(0.05, 0.15))

    logger.info("PX Solver: OS mouse -> screen (%d, %d)", target_sx, target_sy)
    os_mouse_move(target_sx, target_sy, duration=random_module.uniform(0.4, 0.8))
    await asyncio_module.sleep(random_module.uniform(0.05, 0.15))

    max_hold = 15.0
    logger.info(
        "PX Solver: mouseDown -- holding until completion (max %.0fs)...", max_hold
    )
    pyautogui.mouseDown()

    hold_start = asyncio_module.get_event_loop().time()
    challenge_completed = False

    try:
        while True:
            await asyncio_module.sleep(0.3)
            elapsed = asyncio_module.get_event_loop().time() - hold_start

            try:
                for frame in page.frames:
                    try:
                        done_btn = frame.get_by_role(
                            "button", name="Human Challenge completed"
                        )
                        if await done_btn.count() > 0:
                            challenge_completed = True
                            logger.info(
                                "PX Solver: Challenge completed detected at %.1fs!",
                                elapsed,
                            )
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            if challenge_completed:
                break

            try:
                content = (await page.content()).lower()
                if "px-captcha" not in content and "press & hold" not in content:
                    challenge_completed = True
                    logger.info("PX Solver: Challenge markers gone at %.1fs!", elapsed)
                    break
            except Exception:
                challenge_completed = True
                logger.info("PX Solver: Page detached at %.1fs -- success.", elapsed)
                break

            if elapsed >= max_hold:
                logger.warning(
                    "PX Solver: Max hold time (%.0fs) reached without completion.",
                    max_hold,
                )
                break
    finally:
        pyautogui.mouseUp()
        final_elapsed = asyncio_module.get_event_loop().time() - hold_start
        logger.info("PX Solver: mouseUp after %.1fs.", final_elapsed)

    await asyncio_module.sleep(1.0)

    try:
        content = (await page.content()).lower()
    except Exception:
        logger.info("PX Solver: Page detached after hold -- success.")
        return True

    if not any(m in content for m in ("px-captcha", "press & hold", "human challenge")):
        logger.info("PX Solver: No challenge markers in page content -- success.")
        return True

    for frame in page.frames:
        try:
            done_btn = frame.get_by_role("button", name="Human Challenge completed")
            if await done_btn.count() > 0:
                logger.info("PX Solver: 'Human Challenge completed' button found!")
                return True
        except Exception:
            continue

    for frame in page.frames:
        try:
            ph = frame.get_by_role("button", name="Press & Hold")
            if await ph.count() > 0 and await ph.first.is_visible():
                logger.info(
                    "PX Solver: Press & Hold button still visible -- hold failed."
                )
                return False
        except Exception:
            continue

    logger.info("PX Solver: No challenge elements remain -- success.")
    return True
