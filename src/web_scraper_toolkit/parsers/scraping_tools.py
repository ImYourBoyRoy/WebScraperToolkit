# ./src/web_scraper_toolkit/parsers/scraping_tools.py
"""
Scraping Tools Collection
=========================

A suite of high-level tools for specific scraping tasks.
Includes markdown conversion, metadata extraction, and SERP parsing helpers.
Used heavily by the MCP server and CLI.

Usage:
    markdown = read_website_markdown(url)
    results = general_web_search(query)

Key Tools:
    - read_website_markdown: Full page to MD.
    - read_website_content: Raw text.
    - general_web_search: DuckDuckGo interface.
"""

import asyncio
import logging
import re
import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus, urlparse, urljoin
from typing import Optional, Dict, Any, Union

from bs4 import BeautifulSoup

# Relative imports for the package
# Relative imports regarding PlaywrightManager moved to function scope for circular dependency resolution.
from .serp_parser import SerpParser
from .html_to_markdown import MarkdownConverter
from ..core.config import ScraperConfig


logger = logging.getLogger(__name__)


async def _arun_scrape(
    website_url: str, config: Optional[Union[Dict[str, Any], ScraperConfig]] = None
) -> str:
    """Async helper for scraping."""
    manager = None
    config = config or {}
    try:
        from ..browser.playwright_handler import PlaywrightManager

        manager = PlaywrightManager(config=config)
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
    website_url: str, config: Optional[Union[Dict[str, Any], ScraperConfig]] = None
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
    config: Optional[Union[Dict[str, Any], ScraperConfig]] = None,
    selector: Optional[str] = None,
    max_length: Optional[int] = None,
) -> str:
    """Async helper for scraping and converting to Markdown."""
    manager = None
    config = config or {}
    try:
        from ..browser.playwright_handler import PlaywrightManager

        manager = PlaywrightManager(config=config)
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
                markdown = markdown[:max_length] + "\n\n... [Truncated due to max_length]"


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
    config: Optional[Union[Dict[str, Any], ScraperConfig]] = None,
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
            return asyncio.run(_arun_scrape_markdown(website_url, config, selector, max_length))
    except RuntimeError:
        return asyncio.run(_arun_scrape_markdown(website_url, config, selector, max_length))


def extract_metadata(
    website_url: str, config: Optional[Union[Dict[str, Any], ScraperConfig]] = None
) -> str:
    """
    Extracts semantic metadata (JSON-LD, OpenGraph, Twitter Cards) from a URL.
    This provides highly structured data often missed by text scrapers.
    """
    config = config or {}
    try:
        # We use sync wrapper pattern matching other tools
        loop = asyncio.get_running_loop()
        if loop.is_running():
            # We need a native async implementation if called from async context,
            # but for now we reuse the pattern:
            future = asyncio.run_coroutine_threadsafe(
                _arun_extract_metadata(website_url, config), loop
            )
            return future.result()
        else:
            return asyncio.run(_arun_extract_metadata(website_url, config))
    except RuntimeError:
        return asyncio.run(_arun_extract_metadata(website_url, config))


async def _arun_extract_metadata(
    website_url: str, config: Optional[Union[Dict[str, Any], ScraperConfig]] = None
) -> str:
    from ..browser.playwright_handler import PlaywrightManager

    manager = PlaywrightManager(config=config)
    await manager.start()
    try:
        content, final_url, status = await manager.smart_fetch(url=website_url)
        if status != 200 or not content:
            return f"Error: Could not retrieve content from {website_url}"

        soup = BeautifulSoup(content, "lxml")
        output = f"=== METADATA REPORT: {final_url} ===\n\n"

        # 1. JSON-LD (The Gold Mine)
        json_lds = soup.find_all("script", type="application/ld+json")
        if json_lds:
            output += "## JSON-LD Structures found:\n"
            for i, script in enumerate(json_lds):
                try:
                    # Basic cleaning of script text
                    data = script.string
                    if data:
                        output += f"--- JSON-LD #{i + 1} ---\n{data.strip()}\n\n"
                except Exception:
                    pass
        else:
            output += "## No JSON-LD found.\n\n"

        # 2. Meta Tags (OpenGraph / Twitter)
        output += "## Meta Tags:\n"
        path_metadata = {}
        for meta in soup.find_all("meta"):
            name = meta.get("name") or meta.get("property")
            content = meta.get("content")
            if name and content:
                if any(
                    x in name
                    for x in ["og:", "twitter:", "description", "keywords", "author"]
                ):
                    path_metadata[name] = content

        for k, v in path_metadata.items():
            output += f"- {k}: {v}\n"

        return output
    finally:
        await manager.stop()


def capture_screenshot(
    website_url: str,
    output_path: str,
    config: Optional[Union[Dict[str, Any], ScraperConfig]] = None,
) -> str:
    """Captures a full-page screenshot of the URL."""
    # Simple sync wrapper
    try:
        asyncio.run(_arun_screenshot(website_url, output_path, config))
        return f"Screenshot saved to {output_path}"
    except Exception as e:
        logger.error(f"Screenshot failed: {e}")
        return f"Error: {e}"


async def _arun_screenshot(
    url: str, path: str, config: Optional[Union[Dict[str, Any], ScraperConfig]] = None
):
    config = config or {}
    from ..browser.playwright_handler import PlaywrightManager

    manager = PlaywrightManager(config)
    await manager.start()
    try:
        await manager.capture_screenshot(url, path, full_page=True)
    finally:
        await manager.stop()


def save_as_pdf(
    website_url: str,
    output_path: str,
    config: Optional[Union[Dict[str, Any], ScraperConfig]] = None,
) -> str:
    """Saves the URL as a PDF (Headless only)."""
    try:
        asyncio.run(_arun_pdf(website_url, output_path, config))
        return f"PDF saved to {output_path}"
    except Exception as e:
        logger.error(f"PDF failed: {e}")
        return f"Error: {e}"


async def _arun_pdf(
    url: str, path: str, config: Optional[Union[Dict[str, Any], ScraperConfig]] = None
):
    config = config or {}
    # Force headless for PDF
    if "scraper_settings" not in config:
        config["scraper_settings"] = {}
    config["scraper_settings"]["headless"] = True

    config["scraper_settings"]["headless"] = True

    from ..browser.playwright_handler import PlaywrightManager

    manager = PlaywrightManager(config)
    await manager.start()
    try:
        await manager.save_pdf(url, path)
    finally:
        await manager.stop()


async def _arun_search(
    search_query: str, config: Optional[Union[Dict[str, Any], ScraperConfig]] = None
) -> str:
    """Enhanced search using DuckDuckGo (HTML version) to avoid blocks."""
    manager = None
    config = config or {}
    try:
        # DDG operators are simpler
        enhanced_query = search_query
        if "CEO" in search_query or "leadership" in search_query:
            enhanced_query = (
                f"{search_query} site:linkedin.com"  # Simplified site search for DDG
            )

        # Use html.duckduckgo.com for easier scraping / less blocking
        search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(enhanced_query)}"

        search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(enhanced_query)}"

        from ..browser.playwright_handler import PlaywrightManager

        manager = PlaywrightManager(config=config)
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
    search_query: str, config: Optional[Union[Dict[str, Any], ScraperConfig]] = None
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


def get_sitemap_urls(*args, **kwargs) -> str:
    """
    Finds, intelligently filters, and prioritizes URLs from a website's sitemap.
    This version is upgraded to handle sitemap index files (which point to other sitemaps)
    as well as regular sitemaps. It dynamically finds a URL from the input.
    """
    # 1. Find the target URL from the function arguments (this part is unchanged)
    full_input_str = " ".join(map(str, args)) + " ".join(map(str, kwargs.values()))
    url_pattern = re.compile(r'https?://[^\s<>"]+|www\.[^\s<>"]+')
    match = url_pattern.search(full_input_str)

    if not match:
        return "Error: No valid URL could be found in the input. Please provide a valid URL."

    target_url = match.group(0)
    sitemap_url = urljoin(target_url, "/sitemap.xml")
    logger.info(f"Attempting to fetch sitemap from: {sitemap_url}")

    all_urls = []

    try:
        # This part for fetching and parsing the index is unchanged
        response = requests.get(
            sitemap_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

        if root.tag == f"{namespace}sitemapindex":
            sitemap_links = [
                elem.text for elem in root.findall(f".//{namespace}loc") if elem.text
            ]
            for link in sitemap_links:
                try:
                    nested_response = requests.get(
                        link, timeout=10, headers={"User-Agent": "Mozilla/5.0"}
                    )
                    nested_response.raise_for_status()
                    nested_root = ET.fromstring(nested_response.content)
                    urls = [
                        elem.text
                        for elem in nested_root.findall(f".//{namespace}loc")
                        if elem.text
                    ]
                    all_urls.extend(urls)
                except requests.RequestException as e:
                    logger.warning(
                        f"Could not fetch or parse nested sitemap {link}: {e}"
                    )
                    continue
        elif root.tag == f"{namespace}urlset":
            urls = [
                elem.text for elem in root.findall(f".//{namespace}loc") if elem.text
            ]
            all_urls.extend(urls)
        else:
            return "Error: The XML file at /sitemap.xml is not a valid sitemap or sitemap index."

        if not all_urls:
            return "Sitemap found, but it contains no URLs."

        priority_keywords = [
            "about",
            "contact",
            "team",
            "leadership",
            "management",
            "careers",
            "news",
        ]
        exclude_keywords = [
            # E-commerce
            "/product/",
            "/cart/",
            "/checkout/",
            "/order-",
            # User Accounts
            "/my-account/",
            "/login/",
            "/log-in",
            "/register",
            "/registration",
            "/profile",
            "/dashboard",
            "/password",
            # CMS & Archives
            "/tag/",
            "/category/",
            "/author/",
            "/wp-content/",
            "/uploads/",
            "/page/",
            "?s=",
            # Learning Management Systems (LMS)
            "/courses/",
            "/lessons/",
            "/topic/",
            "/quiz/",
            "/certificates/",
            "sfwd-",
            "/ldgr_group_code/",
            # Forums / Groups
            "/groups/",
            # Forms & Procedural
            "/inquiry",
            "/form/",
            # Unlikely to contain core info
            "/testimonials/",
        ]

        priority_urls = []
        other_urls = []

        unique_urls = sorted(list(set(all_urls)))

        for url in unique_urls:
            url_lower = url.lower()

            if any(keyword in url_lower for keyword in exclude_keywords):
                continue

            if any(keyword in url_lower for keyword in priority_keywords):
                priority_urls.append(url)
            else:
                other_urls.append(url)

        total_found = len(unique_urls)
        total_returned = len(priority_urls) + min(len(other_urls), 15)

        output = f"Sitemap analysis complete. Found {total_found} unique URLs, returning the {total_returned} most relevant.\n\n"

        if priority_urls:
            output += "=== Priority Pages (About, Contact, Team, etc.) ===\n"
            output += "\n".join(priority_urls) + "\n\n"

        if other_urls:
            output += "=== Other Relevant Pages (Limited to 15) ===\n"
            output += "\n".join(other_urls[:15]) + "\n"

        return output

    except requests.RequestException as e:
        return f"Sitemap not found or could not be accessed. Error: {e}"
    except ET.ParseError as e:
        return f"Error parsing the sitemap XML file: {e}"


async def _arun_deep_research(
    search_query: str, config: Optional[Union[Dict[str, Any], ScraperConfig]] = None
) -> str:
    """Async helper for deep research using DuckDuckGo + Content Crawl."""
    logger.info(f"Executing Deep Research (via DDG) for query: {search_query}")
    final_report = f"=== Deep Research Report for '{search_query}' ===\n\n"
    manager = None
    config = config or {}

    try:
        from ..browser.playwright_handler import PlaywrightManager

        manager = PlaywrightManager(config=config)
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
    search_query: str, config: Optional[Union[Dict[str, Any], ScraperConfig]] = None
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

    Args:
        field_path (str): The dot-notation path of the field you are finished searching for.
        reasoning (str): A brief explanation of why you are stopping the search for this field.
    """
    log_message = (
        f"Agent has concluded research for field '{field_path}'. Reason: {reasoning}"
    )
    logger.info(log_message)
    return log_message


def clean_text(text: str) -> str:
    """
    Cleans text by removing extra whitespaces and standardizing format.
    """
    if not text:
        return ""
    # Replace multiple spaces/newlines with single space
    return re.sub(r"\s+", " ", text).strip()
