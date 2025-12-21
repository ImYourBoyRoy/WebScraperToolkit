# ./src/web_scraper_toolkit/parsers/search/search.py
"""
Search Tools
============

Tools for performing web searches and deep research using DuckDuckGo and other engines.
"""

import asyncio
import logging
from urllib.parse import quote_plus, urlparse
from typing import Optional, Dict, Any, Union

from bs4 import BeautifulSoup

from .serp_parser import SerpParser
from ..config import ParserConfig
from ...browser.config import BrowserConfig

logger = logging.getLogger(__name__)


async def _arun_search(
    search_query: str, config: Optional[Union[Dict[str, Any], ParserConfig]] = None
) -> str:
    """Enhanced search using DuckDuckGo (HTML version) to avoid blocks."""
    manager = None

    try:
        # DDG operators are simpler
        enhanced_query = search_query
        if "CEO" in search_query or "leadership" in search_query:
            enhanced_query = (
                f"{search_query} site:linkedin.com"  # Simplified site search for DDG
            )

        # Use html.duckduckgo.com for easier scraping / less blocking
        search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(enhanced_query)}"

        from ...browser.playwright_handler import PlaywrightManager

        manager = PlaywrightManager(config=BrowserConfig())
        await manager.start()

        # DDG HTML often checks for 'content-type' form submission, but GET usually works for simple queries.

        content_html, final_url, status_code = await manager.smart_fetch(url=search_url)

        if not content_html or status_code != 200:
            return f"Error: Failed to retrieve search results. Status: {status_code}"

        # Use simple DDG parser
        results = SerpParser.parse_ddg_html(content_html, final_url)

        if not results:
            # Fallback: maybe we got a captcha or it's empty.
            return "No search results found (or access blocked)."

        # Return more results with better structure
        output_str = f"Found {len(results)} results for '{search_query}':\n\n"

        # Categorize results by domain authority
        prioritized_results = []
        regular_results = []

        priority_domains = [
            "linkedin.com",
            "bloomberg.com",
            "crunchbase.com",
            "reuters.com",
            "wsj.com",
        ]

        for item in results[:15]:
            raw_url = item.get("url", "")
            # normalise URL to plain str
            if isinstance(raw_url, (bytes, bytearray)):
                raw_url = raw_url.decode("utf-8", errors="ignore")

            domain = urlparse(raw_url).netloc.lower() if raw_url else ""

            if any(pd in domain for pd in priority_domains):
                prioritized_results.append(item)
            else:
                regular_results.append(item)

        # Format output with priority results first
        result_num = 1
        if prioritized_results:
            output_str += "=== HIGH-AUTHORITY SOURCES ===\n"
            for item in prioritized_results[:8]:
                output_str += f"{result_num}. {item.get('title')}\n"
                output_str += f"   URL: {item.get('url')}\n"
                output_str += f"   Snippet: {item.get('snippet')}\n\n"
                result_num += 1

        output_str += "\n=== ADDITIONAL SOURCES ===\n"
        for item in regular_results[:12]:
            output_str += f"{result_num}. {item.get('title')}\n"
            output_str += f"   URL: {item.get('url')}\n"
            output_str += f"   Snippet: {item.get('snippet')}\n\n"
            result_num += 1

        return output_str

    except Exception as e:
        logger.error(
            f"An error occurred during web search for '{search_query}': {e}",
            exc_info=True,
        )
        return f"An error occurred during web search: {str(e)}"
    finally:
        if manager:
            await manager.stop()


def general_web_search(
    search_query: str, config: Optional[Union[Dict[str, Any], ParserConfig]] = None
) -> str:
    """
    Performs a web search using a search engine to find information or relevant URLs.
    Returns a formatted list of search results.

    Args:
        search_query (str): The query to search for.
    """
    logger.info(f"Executing general_web_search for query: {search_query}")
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                _arun_search(search_query, config), loop
            )
            return future.result()
        else:
            return asyncio.run(_arun_search(search_query, config))
    except RuntimeError:
        return asyncio.run(_arun_search(search_query, config))


async def _arun_deep_research(
    search_query: str, config: Optional[Union[Dict[str, Any], ParserConfig]] = None
) -> str:
    """Async helper for deep research using DuckDuckGo + Content Crawl."""
    logger.info(f"Executing Deep Research (via DDG) for query: {search_query}")
    final_report = f"=== Deep Research Report for '{search_query}' ===\n\n"
    manager = None

    try:
        from ...browser.playwright_handler import PlaywrightManager

        manager = PlaywrightManager(config=BrowserConfig())
        await manager.start()

        # --- 1. Perform Search (Reuse DDG logic directly if possible, but distinct here) ---
        search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(search_query)}"

        page, context = await manager.get_new_page()
        if not page:
            return "Error: Could not create browser page."

        content_html, final_url, status_code = await manager.fetch_page_content(
            page=page, url=search_url
        )
        await page.close()
        if context:
            await context.close()

        if not content_html:
            return f"Error: Failed to search. Status: {status_code}"

        # --- 2. Parse Results ---
        results = SerpParser.parse_ddg_html(content_html, final_url)

        final_report += "## Search Summary (DuckDuckGo)\n"
        if not results:
            final_report += "No results found.\n"
            return final_report

        for i, res in enumerate(results[:5]):
            final_report += f"{i + 1}. {res.get('title')}\n"
            final_report += f"   URL: {res.get('url')}\n"
            final_report += f"   Snippet: {res.get('snippet')}\n\n"

        # --- 3. Crawl Top Organic Results ---
        final_report += "---\n\n"

        # Filter for actual content URLs (skip pdfs/docs if desirable, but simple check for now)
        urls_to_crawl = [res["url"] for res in results[:3] if res.get("url")]

        for i, url_to_crawl in enumerate(urls_to_crawl):
            logger.info(f"Crawling top result #{i + 1}: {url_to_crawl}")

            page, context = await manager.get_new_page()
            if not page:
                continue

            page_content, _, _ = await manager.fetch_page_content(
                page=page, url=url_to_crawl
            )

            final_report += f"## Content from Result #{i + 1}: {url_to_crawl}\n"
            if page_content:
                soup = BeautifulSoup(page_content, "lxml")
                for tag in soup(
                    ["script", "style", "nav", "footer", "header", "aside", "noscript"]
                ):
                    tag.decompose()
                text = soup.get_text(separator=" ", strip=True)
                final_report += f"{text[:4000]}...\n\n"
            else:
                final_report += "Could not retrieve content.\n\n"

            await page.close()
            if context:
                await context.close()

        return final_report

    except Exception as e:
        logger.error(f"Deep research failed for '{search_query}': {e}", exc_info=True)
        return f"Error: {str(e)}"
    finally:
        if manager:
            await manager.stop()


def deep_research_with_google(
    search_query: str, config: Optional[Union[Dict[str, Any], ParserConfig]] = None
) -> str:
    """
    Performs a deep research task. It searches using DuckDuckGo (more reliable locally),
    parses the results, and then crawls the content of the top 2-3 links.
    Use this when you need comprehensive information on a topic, person, or company
    that is not available from a single known website.

    Args:
        search_query (str): The research query.
    """
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                _arun_deep_research(search_query, config), loop
            )
            return future.result()
        else:
            return asyncio.run(_arun_deep_research(search_query, config))
    except RuntimeError:
        return asyncio.run(_arun_deep_research(search_query, config))


def finish_research_for_field(field_path: str, reasoning: str) -> str:
    """
    Call this tool when you have exhausted all methods for finding a specific field
    and have concluded that it cannot be found. This signals that you are moving on.
    """
    return f"Field '{field_path}' marked as not found. Reasoning: {reasoning}"
