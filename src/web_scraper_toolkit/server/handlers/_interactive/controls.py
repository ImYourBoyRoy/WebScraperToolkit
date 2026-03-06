# ./src/web_scraper_toolkit/server/handlers/_interactive/controls.py
"""
Implement granular browser control actions used by InteractiveSession.
Run: imported by `server.handlers.interactive` and called by MCP-interactive tools.
Inputs: active Playwright page object and normalized selector/key/scroll arguments.
Outputs: structured per-action dictionaries suitable for JSON envelopes.
Side effects: mutates browser UI state (focus, keyboard events, scrolling, hover).
Operational notes: validates inputs and enforces hard caps for LLM-friendly payloads.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from playwright.async_api import Page

WAIT_STATES = {"attached", "detached", "visible", "hidden"}
SCROLL_DIRECTIONS = {"up", "down", "left", "right"}

INTERACTION_MAP_EVAL_JS = """
(payload) => {
  const rootSelector = payload.rootSelector || "body";
  const maxElements = Math.max(1, Math.min(200, Number(payload.maxElements || 60)));
  const includeHidden = Boolean(payload.includeHidden);
  let root = document.body;
  try {
    root = document.querySelector(rootSelector) || document.body;
  } catch {
    root = document.body;
  }
  const query = [
    "a[href]",
    "button",
    "input",
    "select",
    "textarea",
    "summary",
    "[role='button']",
    "[role='link']",
    "[role='menuitem']",
    "[contenteditable='true']",
    "[tabindex]"
  ].join(",");
  const compact = (value, maxLen = 140) => {
    if (!value) return "";
    return String(value).replace(/\\s+/g, " ").trim().slice(0, maxLen);
  };
  const isVisible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (!style || style.visibility === "hidden" || style.display === "none") {
      return false;
    }
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const selectorHint = (el) => {
    if (!el) return "";
    const id = compact(el.id, 80);
    if (id) return `#${id}`;
    const dataTestId = compact(el.getAttribute("data-testid"), 80);
    if (dataTestId) return `${el.tagName.toLowerCase()}[data-testid="${dataTestId}"]`;
    const name = compact(el.getAttribute("name"), 80);
    if (name) return `${el.tagName.toLowerCase()}[name="${name}"]`;
    const ariaLabel = compact(el.getAttribute("aria-label"), 80);
    if (ariaLabel) return `${el.tagName.toLowerCase()}[aria-label="${ariaLabel}"]`;
    const classes = compact(el.className || "", 120)
      .split(" ")
      .filter(Boolean)
      .slice(0, 2)
      .join(".");
    if (classes) return `${el.tagName.toLowerCase()}.${classes}`;
    return el.tagName.toLowerCase();
  };
  const nodes = Array.from(root.querySelectorAll(query));
  const elements = [];
  for (const node of nodes) {
    if (elements.length >= maxElements) break;
    if (!includeHidden && !isVisible(node)) continue;
    const rect = node.getBoundingClientRect();
    const textCandidate =
      compact(node.getAttribute("aria-label")) ||
      compact(node.innerText) ||
      compact(node.textContent) ||
      compact(node.getAttribute("placeholder")) ||
      compact(node.getAttribute("title")) ||
      compact(node.getAttribute("value"));
    elements.push({
      index: elements.length,
      tag: String(node.tagName || "").toLowerCase(),
      role: compact(node.getAttribute("role"), 40),
      type: compact(node.getAttribute("type"), 40),
      text: textCandidate,
      href: compact(node.getAttribute("href"), 240),
      selector_hint: selectorHint(node),
      visible: isVisible(node),
      bbox: {
        x: Math.round(rect.x || 0),
        y: Math.round(rect.y || 0),
        width: Math.round(rect.width || 0),
        height: Math.round(rect.height || 0)
      }
    });
  }
  return {
    root_selector: rootSelector,
    count: elements.length,
    truncated: nodes.length > elements.length,
    elements
  };
}
"""


def _resolve_scroll_deltas(direction: str, amount: int) -> tuple[int, int]:
    if direction == "up":
        return (0, -amount)
    if direction == "left":
        return (-amount, 0)
    if direction == "right":
        return (amount, 0)
    return (0, amount)


async def run_wait_for(
    page: Page,
    selector: Optional[str],
    state: str,
    timeout_ms: int,
) -> Dict[str, Any]:
    """Wait for selector state transition or fixed timeout."""
    normalized_state = (state or "visible").strip().lower()
    if normalized_state not in WAIT_STATES:
        raise ValueError(
            f"Invalid wait state '{state}'. Expected one of: {sorted(WAIT_STATES)}"
        )
    timeout_value = max(0, int(timeout_ms))

    if selector:
        await page.wait_for_selector(
            selector,
            state=normalized_state,
            timeout=timeout_value,
        )
    else:
        await page.wait_for_timeout(timeout_value)

    return {
        "selector": selector,
        "state": normalized_state,
        "timeout_ms": timeout_value,
    }


async def run_press_key(
    page: Page,
    key: str,
    selector: Optional[str],
    delay_ms: int,
) -> Dict[str, Any]:
    """Press keyboard key with optional pre-focus selector targeting."""
    normalized_key = (key or "").strip()
    if not normalized_key:
        raise ValueError("Key must be a non-empty string.")

    if selector:
        await page.locator(selector).first.focus(timeout=10000)

    delay_value = max(0, int(delay_ms))
    await page.keyboard.press(normalized_key, delay=delay_value)
    await page.wait_for_timeout(250)

    return {
        "key": normalized_key,
        "selector": selector,
        "delay_ms": delay_value,
    }


async def run_scroll(
    page: Page,
    direction: str,
    amount: int,
    selector: Optional[str],
    smooth: bool,
) -> Dict[str, Any]:
    """Scroll page or element and return resulting scroll position metadata."""
    normalized_direction = (direction or "down").strip().lower()
    if normalized_direction not in SCROLL_DIRECTIONS:
        raise ValueError(
            f"Invalid scroll direction '{direction}'. Expected one of: {sorted(SCROLL_DIRECTIONS)}"
        )
    amount_value = max(1, int(amount))
    dx, dy = _resolve_scroll_deltas(normalized_direction, amount_value)

    if selector:
        position = await page.locator(selector).first.evaluate(
            """
            (el, payload) => {
              const { dx, dy, smooth } = payload;
              const behavior = smooth ? "smooth" : "auto";
              if (typeof el.scrollBy === "function") {
                el.scrollBy({ left: dx, top: dy, behavior });
              } else {
                el.scrollLeft = (el.scrollLeft || 0) + dx;
                el.scrollTop = (el.scrollTop || 0) + dy;
              }
              return {
                scrollLeft: Number(el.scrollLeft || 0),
                scrollTop: Number(el.scrollTop || 0),
              };
            }
            """,
            {"dx": dx, "dy": dy, "smooth": bool(smooth)},
        )
    else:
        position = await page.evaluate(
            """
            (payload) => {
              const { dx, dy, smooth } = payload;
              const behavior = smooth ? "smooth" : "auto";
              window.scrollBy({ left: dx, top: dy, behavior });
              return {
                scrollX: Number(window.scrollX || 0),
                scrollY: Number(window.scrollY || 0),
              };
            }
            """,
            {"dx": dx, "dy": dy, "smooth": bool(smooth)},
        )

    await page.wait_for_timeout(400 if smooth else 100)
    return {
        "direction": normalized_direction,
        "amount": amount_value,
        "selector": selector,
        "position": position,
    }


async def run_hover(page: Page, selector: str) -> Dict[str, Any]:
    """Hover over selector and return compact metadata."""
    await page.hover(selector, timeout=10000)
    await page.wait_for_timeout(300)
    return {"selector": selector}


async def run_interaction_map(
    page: Page,
    selector: Optional[str],
    max_elements: int,
    include_hidden: bool,
) -> Dict[str, Any]:
    """Return a compact interaction map tailored for agentic element targeting."""
    max_items = max(1, min(int(max_elements), 200))
    root_selector = (selector or "body").strip() or "body"
    return await page.evaluate(
        INTERACTION_MAP_EVAL_JS,
        {
            "rootSelector": root_selector,
            "maxElements": max_items,
            "includeHidden": bool(include_hidden),
        },
    )


_A11Y_ALLOWED_KEYS = {
    "role",
    "name",
    "value",
    "description",
    "keyshortcuts",
    "roledescription",
    "valuetext",
    "disabled",
    "expanded",
    "focused",
    "modal",
    "multiline",
    "multiselectable",
    "readonly",
    "required",
    "selected",
    "checked",
    "pressed",
    "level",
    "orientation",
    "url",
}


def _truncate_text(value: str, max_text_length: int) -> str:
    if len(value) <= max_text_length:
        return value
    return f"{value[:max_text_length]}…"


def _normalize_a11y_value(value: Any, max_text_length: int) -> Any:
    if isinstance(value, str):
        return _truncate_text(value, max_text_length)
    return value


def _sanitize_a11y_node(node: Dict[str, Any], max_text_length: int) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key, value in node.items():
        if key == "children":
            continue
        if key not in _A11Y_ALLOWED_KEYS:
            continue
        if value is None:
            continue
        cleaned[key] = _normalize_a11y_value(value, max_text_length)
    if "role" not in cleaned:
        cleaned["role"] = "unknown"
    return cleaned


def _trim_accessibility_tree(
    root: Optional[Dict[str, Any]],
    max_nodes: int,
    max_text_length: int,
) -> Dict[str, Any]:
    node_cap = max(1, min(int(max_nodes), 1000))
    text_cap = max(20, min(int(max_text_length), 1000))
    count = 0
    truncated = False

    def walk(node: Any) -> Optional[Dict[str, Any]]:
        nonlocal count, truncated
        if not isinstance(node, dict):
            return None
        if count >= node_cap:
            truncated = True
            return None
        count += 1
        cleaned = _sanitize_a11y_node(node, text_cap)
        raw_children = node.get("children")
        if isinstance(raw_children, list) and raw_children:
            kept_children = []
            for child in raw_children:
                trimmed = walk(child)
                if trimmed is not None:
                    kept_children.append(trimmed)
            if kept_children:
                cleaned["children"] = kept_children
        return cleaned

    trimmed_tree = walk(root)
    return {
        "tree": trimmed_tree,
        "node_count": count,
        "truncated": truncated,
        "max_nodes": node_cap,
        "max_text_length": text_cap,
    }


async def run_accessibility_tree(
    page: Page,
    selector: Optional[str],
    interesting_only: bool,
    max_nodes: int,
    max_text_length: int,
) -> Dict[str, Any]:
    """Capture and trim a Playwright accessibility snapshot for agent consumption."""
    root_handle = None
    root_selector = (selector or "").strip()
    if root_selector:
        root_handle = await page.locator(root_selector).first.element_handle(
            timeout=10000
        )
        if root_handle is None:
            raise ValueError(f"No element matched selector: {root_selector}")

    raw_tree = await page.accessibility.snapshot(
        root=root_handle,
        interesting_only=bool(interesting_only),
    )
    trimmed = _trim_accessibility_tree(
        raw_tree, max_nodes=max_nodes, max_text_length=max_text_length
    )
    trimmed["interesting_only"] = bool(interesting_only)
    trimmed["root_selector"] = root_selector or "document"
    return trimmed
