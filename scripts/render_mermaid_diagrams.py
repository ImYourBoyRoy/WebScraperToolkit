# ./scripts/render_mermaid_diagrams.py
"""
Render Mermaid `.mmd` diagrams into high-resolution static images for README/PyPI compatibility.
Run: `python ./scripts/render_mermaid_diagrams.py [--diagrams-dir docs/diagrams --output-dir docs/assets/diagrams]`.
Inputs: Mermaid source files (`*.mmd`), render theme settings, output format, and sizing flags.
Outputs: One rendered image per diagram source (default `.webp`) and an optional quality manifest.
Side effects: Writes image files to output directory and fetches Mermaid ESM from CDN at render time.
Operational notes: Requires Playwright + Chromium (`playwright install`); defaults are tuned for large flowcharts.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from PIL import Image
from playwright.async_api import Browser, Page, async_playwright

MERMAID_ESM_URL = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs"


@dataclass(frozen=True)
class RenderSettings:
    theme: str
    output_format: str
    quality: int
    min_long_side: int
    max_long_side: int
    padding: int
    device_scale_factor: float
    viewport_width: int
    viewport_height: int


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render Mermaid .mmd files to high-resolution static images."
    )
    parser.add_argument(
        "--diagrams-dir",
        default="docs/diagrams",
        help="Directory containing .mmd Mermaid source files.",
    )
    parser.add_argument(
        "--output-dir",
        default="docs/assets/diagrams",
        help="Directory for rendered image outputs.",
    )
    parser.add_argument(
        "--theme",
        default="neutral",
        choices=["default", "neutral", "dark", "forest", "base"],
        help="Mermaid theme used during render.",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        default="webp",
        choices=["webp", "png", "jpeg"],
        help="Rendered image format.",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=95,
        help="Output quality for lossy formats (JPEG/WEBP).",
    )
    parser.add_argument(
        "--min-long-side",
        type=int,
        default=2600,
        help="Minimum size for the largest output dimension (width or height).",
    )
    parser.add_argument(
        "--max-long-side",
        type=int,
        default=8000,
        help="Maximum size for the largest output dimension (width or height).",
    )
    parser.add_argument(
        "--padding",
        type=int,
        default=80,
        help="Diagram padding around rendered SVG in pixels.",
    )
    parser.add_argument(
        "--device-scale-factor",
        type=float,
        default=2.0,
        help="Playwright context device scale factor for crisp output.",
    )
    parser.add_argument(
        "--viewport-width",
        type=int,
        default=3600,
        help="Render viewport width.",
    )
    parser.add_argument(
        "--viewport-height",
        type=int,
        default=2400,
        help="Render viewport height.",
    )
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="Write a JSON manifest with rendered output metadata.",
    )
    return parser.parse_args()


def _iter_diagram_files(diagrams_dir: Path) -> Iterable[Path]:
    return sorted(path for path in diagrams_dir.glob("*.mmd") if path.is_file())


def _build_html(diagram_text: str, settings: RenderSettings) -> str:
    escaped_diagram = html.escape(diagram_text)
    theme = json.dumps(settings.theme)
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      html, body {{
        margin: 0;
        padding: 0;
        background: #ffffff;
      }}
      #canvas {{
        padding: {settings.padding}px;
        width: fit-content;
        min-width: 100%;
        box-sizing: border-box;
      }}
      .mermaid {{
        width: max-content;
      }}
    </style>
  </head>
  <body>
    <div id="canvas">
      <pre class="mermaid">{escaped_diagram}</pre>
    </div>
    <script type="module">
      import mermaid from "{MERMAID_ESM_URL}";
      mermaid.initialize({{
        startOnLoad: true,
        theme: {theme},
        securityLevel: "loose",
        flowchart: {{
          useMaxWidth: false,
          htmlLabels: true,
          rankSpacing: 64,
          nodeSpacing: 48,
          curve: "basis"
        }}
      }});
      await mermaid.run({{ querySelector: ".mermaid" }});
      window.__diagramReady = true;
    </script>
  </body>
</html>
"""


async def _render_one(
    *,
    page: Page,
    source_path: Path,
    output_path: Path,
    settings: RenderSettings,
) -> dict:
    diagram_text = source_path.read_text(encoding="utf-8")
    html_content = _build_html(diagram_text, settings)

    await page.set_content(html_content, wait_until="networkidle")
    await page.wait_for_function("() => window.__diagramReady === true")

    svg_locator = page.locator("#canvas svg")
    if await svg_locator.count() == 0:
        raise RuntimeError(f"No SVG produced for {source_path.name}.")

    temp_png_path = output_path.with_suffix(".tmp.png")
    await svg_locator.screenshot(path=str(temp_png_path))

    with Image.open(temp_png_path) as image:
        width, height = image.size
        long_side = max(width, height)
        scale_up = max(settings.min_long_side / max(1, long_side), 1.0)
        scale_down = min(
            settings.max_long_side / max(1.0, long_side * scale_up),
            1.0,
        )
        scale = max(0.01, scale_up * scale_down)

        if abs(scale - 1.0) > 1e-3:
            resized = image.resize(
                (int(round(width * scale)), int(round(height * scale))),
                Image.Resampling.LANCZOS,
            )
        else:
            resized = image.copy()

        save_kwargs = {}
        if settings.output_format in {"webp", "jpeg"}:
            save_kwargs["quality"] = max(1, min(100, int(settings.quality)))
            save_kwargs["method"] = 6 if settings.output_format == "webp" else 0

        resized.save(output_path, format=settings.output_format.upper(), **save_kwargs)
        out_width, out_height = resized.size

    temp_png_path.unlink(missing_ok=True)
    return {
        "source": str(source_path.as_posix()),
        "output": str(output_path.as_posix()),
        "output_width": out_width,
        "output_height": out_height,
        "theme": settings.theme,
        "format": settings.output_format,
    }


async def _run_render(
    *,
    diagram_paths: List[Path],
    output_dir: Path,
    settings: RenderSettings,
) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    async with async_playwright() as playwright:
        browser: Browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={
                "width": settings.viewport_width,
                "height": settings.viewport_height,
            },
            device_scale_factor=settings.device_scale_factor,
        )
        page = await context.new_page()
        for path in diagram_paths:
            output_path = output_dir / f"{path.stem}.{settings.output_format}"
            result = await _render_one(
                page=page,
                source_path=path,
                output_path=output_path,
                settings=settings,
            )
            results.append(result)
            print(
                f"[+] Rendered {path.name} -> {output_path.as_posix()} "
                f"({result['output_width']}x{result['output_height']})"
            )
        await context.close()
        await browser.close()
    return results


def main() -> int:
    args = _parse_args()
    diagrams_dir = Path(args.diagrams_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    if not diagrams_dir.exists():
        raise SystemExit(f"Diagrams directory not found: {diagrams_dir}")

    diagram_paths = list(_iter_diagram_files(diagrams_dir))
    if not diagram_paths:
        raise SystemExit(f"No .mmd files found in: {diagrams_dir}")

    settings = RenderSettings(
        theme=args.theme,
        output_format=str(args.output_format).lower(),
        quality=args.quality,
        min_long_side=max(400, int(args.min_long_side)),
        max_long_side=max(800, int(args.max_long_side)),
        padding=max(0, int(args.padding)),
        device_scale_factor=max(1.0, float(args.device_scale_factor)),
        viewport_width=max(800, int(args.viewport_width)),
        viewport_height=max(600, int(args.viewport_height)),
    )

    results = asyncio.run(
        _run_render(
            diagram_paths=diagram_paths,
            output_dir=output_dir,
            settings=settings,
        )
    )

    if args.write_manifest:
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"[*] Wrote manifest: {manifest_path.as_posix()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
