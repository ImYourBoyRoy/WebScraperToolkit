# ./src/web_scraper_toolkit/browser/solver.py
"""
Cloudflare Spatial Solver
=========================

Logic for handling Cloudflare challenges using coordinate-based interaction.
"""

import logging
import random
from playwright.async_api import Page

logger = logging.getLogger(__name__)


class CloudflareSolver:
    """
    Coordinate-based spatial solver for Cloudflare.
    Simulates human mouse interaction to click verify widgets.
    """

    @staticmethod
    async def solve_spatial(page: Page) -> bool:
        """
        Attempts to solve the Cloudflare visible challenge.
        """
        try:
            # Stabilize
            await page.wait_for_timeout(2000)

            # Find label
            label = page.get_by_text("Verifying you are human")
            if await label.count() == 0:
                label = page.get_by_text("Verify you are human")

            # Iframe Fallback
            if await label.count() == 0:
                for frame in page.frames:
                    try:
                        if (
                            await frame.get_by_text("Verifying you are human").count()
                            > 0
                        ):
                            label = frame.get_by_text("Verifying you are human")
                            break
                    except Exception:
                        continue

            if await label.count() > 0:
                box = await label.bounding_box()
                if box:
                    # OFFSETS: +25px right, +70px down from text
                    target_x = box["x"] + 25
                    target_y = box["y"] + 70

                    logger.info(
                        f"Solver: Clicking Widget at X={int(target_x)}, Y={int(target_y)}"
                    )

                    try:
                        # Human Click (Down -> Wait -> Up)
                        await page.mouse.move(target_x, target_y, steps=10)
                        await page.wait_for_timeout(300)
                        await page.mouse.down()
                        await page.wait_for_timeout(random.randint(150, 300))
                        await page.mouse.up()
                        logger.info("Solver: Interaction sent. Waiting for redirect...")
                    except Exception as mouse_err:
                        # If the page navigates *during* the click (e.g. auto-solve or fast redirect),
                        # we might get "Target page, context or browser has been closed".
                        # This is usually a GOOD sign (we passed).
                        logger.info(
                            f"Solver: Interaction interrupted (likely redirect): {mouse_err}"
                        )

                    # Wait for redirect loop (15s max)
                    for _ in range(15):
                        await page.wait_for_timeout(1000)
                        try:
                            title = await page.title()
                            # Success check: Title changed from challenge
                            if (
                                "Just a moment" not in title
                                and "Attention Required" not in title
                                and "403" not in title
                            ):
                                logger.info(f"Solver: Success! Redirected to {title}")
                                return True
                        except Exception:
                            continue
            else:
                logger.info(
                    "Solver: No 'Verifying' text found. Checking if auto-solved..."
                )
                await page.wait_for_timeout(5000)
                try:
                    if "Just a moment" not in (await page.title()):
                        return True
                except Exception:
                    pass

            return False

        except Exception as e:
            logger.error(f"Solver: Spatial Solver Error: {e}")
            return False
