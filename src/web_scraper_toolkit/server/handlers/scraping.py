# ./src/web_scraper_toolkit/server/tools/scraping.py
"""
Scraping Tools
==============

Core scraping functions (Single URL, Batch, Screenshot, PDF).
"""

from ...parsers.scraping_tools import (
    read_website_markdown,
    read_website_content,
    capture_screenshot,
    save_as_pdf,
)
from ...parsers.config import ParserConfig
from ...browser.playwright_crawler import WebCrawler
from .config import GLOBAL_BROWSER_CONFIG

GLOBAL_PARSER_CONFIG = ParserConfig()


async def scrape_single_url(
    url: str, format: str = "markdown", selector: str = None, max_length: int = 20000
) -> str:
    """Scrapes a single URL to text/markdown."""
    if format == "markdown":
        return await read_website_markdown(
            url,
            config=GLOBAL_PARSER_CONFIG,
            selector=selector,
            max_length=max_length,
        )
    else:
        return await read_website_content(url, config=GLOBAL_PARSER_CONFIG)


async def scrape_batch(urls: list[str], format: str = "markdown") -> dict:
    """Scrapes multiple URLs using WebCrawler."""
    crawler = WebCrawler(config=GLOBAL_BROWSER_CONFIG)
    results = await crawler.run(
        urls=urls,
        output_format=format,
        export=False,
        merge=False,
    )

    output_map = {}
    for i, (content, _) in enumerate(results):
        if content:
            output_map[urls[i]] = content
        else:
            output_map[urls[i]] = "Error: Failed to scrape."

    return output_map


async def take_screenshot(url: str, path: str) -> bool:
    """Captures a screenshot."""
    data = await capture_screenshot(url, path, config=GLOBAL_PARSER_CONFIG)
    return data  # boolean success


async def save_url_pdf(url: str, path: str) -> bool:
    """Saves URL to PDF."""
    data = await save_as_pdf(url, path, config=GLOBAL_PARSER_CONFIG)
    return data  # boolean success
