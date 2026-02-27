# ./src/web_scraper_toolkit/parsers/content.py
"""
Content Extraction Tools
========================

Tools for extracting and cleaning content from websites, including HTML to Markdown conversion.
"""

import asyncio
import logging
import re
from concurrent.futures import Future
from threading import Thread
from typing import Any, Coroutine, Dict, List, Optional, TypeVar, Union

from bs4 import BeautifulSoup

from .html_to_markdown import MarkdownConverter
from .config import ParserConfig
from ..browser.config import BrowserConfig

logger = logging.getLogger(__name__)
T = TypeVar("T")


def _run_coro_sync(coro: Coroutine[Any, Any, T]) -> T:
    """
    Run an async coroutine from synchronous call sites.

    If called from an active event loop thread, execute on a dedicated worker
    thread to avoid deadlocks.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    future: Future[T] = Future()

    def _runner() -> None:
        try:
            future.set_result(asyncio.run(coro))
        except Exception as exc:  # pragma: no cover - surfaced by caller
            future.set_exception(exc)

    worker = Thread(target=_runner, daemon=True)
    worker.start()
    worker.join()
    return future.result()


async def _arun_scrape(
    website_url: str,
    config: Optional[Union[Dict[str, Any], ParserConfig, BrowserConfig]] = None,
) -> str:
    """Async helper for scraping."""
    manager = None
    # Config handling
    # Config handling
    browser_cfg = BrowserConfig()  # default
    if isinstance(config, BrowserConfig):
        browser_cfg = config
    elif isinstance(config, dict):
        # Convert dict to BrowserConfig
        browser_cfg = BrowserConfig(
            headless=config.get("headless", True),
            browser_type=config.get("browser_type", "chromium"),
        )

    try:
        from ..browser.playwright_handler import PlaywrightManager

        manager = PlaywrightManager(config=browser_cfg)
        await manager.start()
        content, final_url, status_code = await manager.smart_fetch(url=website_url)
        if status_code == 200 and content:
            soup = BeautifulSoup(content, "lxml")

            title_tag = soup.find("title")

            title_text = title_tag.get_text(strip=True) if title_tag else "No title"

            # Remove noise
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            # Look for leadership information
            leadership_keywords = [
                "CEO",
                "Chief Executive",
                "Founder",
                "President",
                "Owner",
                "Director",
            ]
            leadership_mentions: List[str] = []
            for text in soup.stripped_strings:
                if any(keyword in text for keyword in leadership_keywords):
                    leadership_mentions.append(text[:200])

            # Look for contact information
            email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
            emails = re.findall(email_pattern, str(soup))
            contact_info = emails[:5]

            # Get main content
            main_content = soup.get_text(separator=" ", strip=True)
            trimmed_main_content = main_content[:15000]

            # Format output
            output = f"=== EXTRACTED FROM: {final_url} ===\n\n"
            output += f"TITLE: {title_text}\n\n"

            if leadership_mentions:
                output += "LEADERSHIP MENTIONS:\n"
                for mention in leadership_mentions[:5]:
                    output += f"- {mention}\n"
                output += "\n"

            if contact_info:
                output += f"CONTACT INFO FOUND: {', '.join(contact_info[:3])}\n\n"

            output += "MAIN CONTENT:\n"
            output += trimmed_main_content

            logger.info(
                f"Successfully scraped and structured {len(main_content)} characters from {final_url}"
            )
            return output
        else:
            return f"Error: Failed to retrieve content from {website_url}. Status code: {status_code}"
    except Exception as e:
        logger.error(
            f"An error occurred while scraping {website_url}: {e}", exc_info=True
        )
        return f"An error occurred while scraping the website: {str(e)}"
    finally:
        if manager:
            await manager.stop()


def read_website_content(
    website_url: str,
    config: Optional[Union[Dict[str, Any], ParserConfig, BrowserConfig]] = None,
) -> str:
    """
    Reads the full, cleaned text content from a given website URL.
    This tool is best for getting a general overview of a page.
    Args:
        website_url (str): The full URL of the website to read.
        config (dict, optional): Configuration dictionary.
    """
    logger.info(f"Executing read_website_content for URL: {website_url}")
    return _run_coro_sync(_arun_scrape(website_url, config))


async def _arun_scrape_markdown(
    website_url: str,
    config: Optional[Union[Dict[str, Any], ParserConfig, BrowserConfig]] = None,
    selector: Optional[str] = None,
    max_length: Optional[int] = None,
) -> str:
    """Async helper for scraping and converting to Markdown."""
    manager = None
    browser_cfg = BrowserConfig()
    if isinstance(config, BrowserConfig):
        browser_cfg = config
    elif isinstance(config, dict):
        browser_cfg = BrowserConfig(
            headless=config.get("headless", True),
            browser_type=config.get("browser_type", "chromium"),
            timeout=config.get("timeout", 30000),
        )
    try:
        from ..browser.playwright_handler import PlaywrightManager

        manager = PlaywrightManager(config=browser_cfg)
        await manager.start()
        # Use Smart Fetch for robustness
        content, final_url, status_code = await manager.smart_fetch(url=website_url)

        if status_code == 200 and content:
            # Selector filtering (BeautifulSoup)
            if selector:
                soup = BeautifulSoup(content, "lxml")
                selected_tag = soup.select_one(selector)
                if selected_tag:
                    content = str(selected_tag)
                else:
                    return f"Error: Selector '{selector}' not found on {website_url}"

            # Convert to Markdown
            markdown = MarkdownConverter.to_markdown(content, base_url=final_url)

            # Max Length Truncation
            if max_length and len(markdown) > max_length:
                markdown = (
                    markdown[:max_length] + "\n\n... [Truncated due to max_length]"
                )

            output = f"=== SCRAPED FROM: {final_url} (MARKDOWN) ===\n\n"
            output += markdown

            logger.info(
                f"Successfully scraped and converted {len(markdown)} chars from {final_url}"
            )
            return output
        else:
            return f"Error: Failed to retrieve content from {website_url}. Status code: {status_code}"
    except Exception as e:
        logger.error(
            f"An error occurred while scraping {website_url}: {e}", exc_info=True
        )
        return f"An error occurred while scraping the website: {str(e)}"
    finally:
        if manager:
            await manager.stop()


def read_website_markdown(
    website_url: str,
    config: Optional[Union[Dict[str, Any], ParserConfig, BrowserConfig]] = None,
    selector: Optional[str] = None,
    max_length: Optional[int] = None,
) -> str:
    """
    Reads the full content from a website and converts it to clean Markdown.
    Supports CSS selectors to scrape specific parts and max_length to limit tokens.

    Args:
        website_url (str): The full URL of the website to read.
        config (dict, optional): Configuration dictionary.
        selector (str): Optional CSS selector to extract only specific content.
        max_length (int): Optional character limit for the output.
    """
    logger.info(f"Executing read_website_markdown for URL: {website_url}")
    return _run_coro_sync(
        _arun_scrape_markdown(website_url, config, selector, max_length)
    )
