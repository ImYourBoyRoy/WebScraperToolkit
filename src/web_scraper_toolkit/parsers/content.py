# ./src/web_scraper_toolkit/parsers/content.py
"""
Content Extraction Tools
========================

Tools for extracting and cleaning content from websites, including HTML to Markdown conversion.
"""

import asyncio
import logging
import re
from typing import Optional, Dict, Any, Union

from bs4 import BeautifulSoup

from .html_to_markdown import MarkdownConverter
from .config import ParserConfig
from ..browser.config import BrowserConfig

logger = logging.getLogger(__name__)


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

            # Extract structured data
            extracted_data = {
                "url": final_url,
                "title": title_tag.text if title_tag else "No title",
                "main_content": "",
                "leadership_mentions": [],
                "contact_info": [],
                "key_facts": [],
            }

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
            for text in soup.stripped_strings:
                if any(keyword in text for keyword in leadership_keywords):
                    extracted_data["leadership_mentions"].append(text[:200])

            # Look for contact information
            email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
            emails = re.findall(email_pattern, str(soup))
            extracted_data["contact_info"].extend(emails[:5])

            # Get main content
            main_content = soup.get_text(separator=" ", strip=True)
            extracted_data["main_content"] = main_content[:15000]  # Increase from 8000

            # Format output
            output = f"=== EXTRACTED FROM: {final_url} ===\n\n"
            output += f"TITLE: {extracted_data['title']}\n\n"

            if extracted_data["leadership_mentions"]:
                output += "LEADERSHIP MENTIONS:\n"
                for mention in extracted_data["leadership_mentions"][:5]:
                    output += f"- {mention}\n"
                output += "\n"

            if extracted_data["contact_info"]:
                output += f"CONTACT INFO FOUND: {', '.join(extracted_data['contact_info'][:3])}\n\n"

            output += "MAIN CONTENT:\n"
            output += extracted_data["main_content"]

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
    # This ensures an asyncio event loop is managed correctly
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                _arun_scrape(website_url, config), loop
            )
            return future.result()
        else:
            return asyncio.run(_arun_scrape(website_url, config))
    except RuntimeError:
        return asyncio.run(_arun_scrape(website_url, config))


async def _arun_scrape_markdown(
    website_url: str,
    config: Optional[Union[Dict[str, Any], ParserConfig]] = None,
    selector: Optional[str] = None,
    max_length: Optional[int] = None,
) -> str:
    """Async helper for scraping and converting to Markdown."""
    manager = None
    browser_cfg = BrowserConfig()
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
    config: Optional[Union[Dict[str, Any], ParserConfig]] = None,
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
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                _arun_scrape_markdown(website_url, config, selector, max_length), loop
            )
            return future.result()
        else:
            return asyncio.run(
                _arun_scrape_markdown(website_url, config, selector, max_length)
            )
    except RuntimeError:
        return asyncio.run(
            _arun_scrape_markdown(website_url, config, selector, max_length)
        )
