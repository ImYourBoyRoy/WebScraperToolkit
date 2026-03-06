# ./src/web_scraper_toolkit/server/handlers/scraping.py
"""
Implement MCP-facing scraping handlers for single and batch URL workflows.
Used by `server.mcp_tools.scraping` to execute core scrape, screenshot, and PDF actions.
Run: Imported by MCP server modules; not a direct command-line entry point.
Inputs: Target URLs, output formats, selectors, and save paths.
Outputs: Scraped payloads or status strings for screenshot/PDF operations.
Side effects: Performs network/browser activity and writes output files when requested.
Operational notes: Keeps stealth/browser behavior delegated to parser/browser modules.
"""

from __future__ import annotations

from ...parsers.scraping_tools import (
    read_website_markdown,
    read_website_content,
    capture_screenshot,
    save_as_pdf,
)
from ...browser.playwright_crawler import WebCrawler
from ...core.runtime import resolve_worker_count
from .config import GLOBAL_BROWSER_CONFIG, get_runtime_config


async def scrape_single_url(
    url: str,
    format: str = "markdown",
    selector: str | None = None,
    max_length: int = 20000,
) -> str:
    """Scrapes a single URL to text/markdown."""
    if format == "markdown":
        return read_website_markdown(
            url,
            config=GLOBAL_BROWSER_CONFIG,
            selector=selector,
            max_length=max_length,
        )
    return read_website_content(url, config=GLOBAL_BROWSER_CONFIG)


async def scrape_batch(
    urls: list[str],
    format: str = "markdown",
    workers: int | None = None,
) -> dict[str, str]:
    """Scrapes multiple URLs using WebCrawler."""
    runtime = get_runtime_config()
    requested_workers = (
        workers
        if workers is not None
        else (
            runtime.concurrency.crawler_default_workers
            if runtime.concurrency.crawler_default_workers > 0
            else "auto"
        )
    )
    worker_count = resolve_worker_count(
        requested_workers,
        cpu_reserve=runtime.concurrency.cpu_reserve,
        max_workers=runtime.concurrency.crawler_max_workers,
        fallback=1,
    )

    crawler = WebCrawler(config=GLOBAL_BROWSER_CONFIG, workers=worker_count)
    results = await crawler.run(
        urls=urls,
        output_format=format,
        export=False,
        merge=False,
    )

    output_map: dict[str, str] = {}
    for i, (content, _) in enumerate(results):
        if content:
            output_map[urls[i]] = content
        else:
            output_map[urls[i]] = "Error: Failed to scrape."

    return output_map


async def take_screenshot(url: str, path: str) -> bool:
    """Captures a screenshot."""
    data = capture_screenshot(url, path, config=GLOBAL_BROWSER_CONFIG)
    return bool(data)


async def save_url_pdf(url: str, path: str) -> bool:
    """Saves URL to PDF."""
    data = save_as_pdf(url, path, config=GLOBAL_BROWSER_CONFIG)
    return bool(data)
