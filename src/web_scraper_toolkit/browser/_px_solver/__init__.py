# ./src/web_scraper_toolkit/browser/_px_solver/__init__.py
"""
Internal PerimeterX solver helpers extracted from the legacy px_solver module.
Used by `browser.px_solver` facade to keep public import paths stable.
Run: imported by browser px solver runtime only.
Inputs: Playwright page/frame handles and mouse-control dependency callables.
Outputs: bool challenge-solve results for hold/click routines.
Side effects: drives OS-level mouse input through injected pyautogui bindings.
Operational notes: private package; public callers should import browser.px_solver.
"""

from .hold import perform_os_hold

__all__ = ["perform_os_hold"]
