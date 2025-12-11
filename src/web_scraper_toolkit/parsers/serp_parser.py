# ./src/web_scraper_toolkit/parsers/serp_parser.py
"""
SERP Parser
===========

Parses Search Engine Results Pages (DuckDuckGo, Google) from HTML.
Extracts titles, snippets, and URLs.

Usage:
    results = SerpParser.parse_ddg_html(html_content)

Key Functions:
    - parse_ddg_html: Extracts organic results from DDG HTML.
"""

import logging
from typing import List, Dict, Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup, Tag

from .utils import normalize_url, truncate_text

logger = logging.getLogger(__name__)


class SerpParser:
    """
    Parses HTML content of Search Engine Result Pages (SERPs)
    to extract search result items like URL, title, and snippet.
    """

    @staticmethod
    def parse_serp(
        html_content: str,
        serp_url: str,  # The URL of the SERP page itself, for resolving relative links
        selector_config: Dict[str, str],
        max_results_to_extract: int = 15
    ) -> List[Dict[str, Optional[str]]]:
        """
        Parses the SERP HTML content based on provided CSS selectors.

        Args:
            html_content: The HTML content of the SERP.
            serp_url: The URL from which the HTML content was fetched (for base URL resolution).
            selector_config: A dictionary containing CSS selectors:
                - "result_item_selector": Selector for the container of each search result.
                - "link_selector": Selector for the <a> tag (or its direct parent) containing the result URL.
                - "title_selector": Selector for the element containing the title text (often same as link_selector).
                - "snippet_selector": Selector for the element containing the descriptive snippet.
            max_results_to_extract: Maximum number of search results to attempt to parse.

        Returns:
            A list of dictionaries, where each dictionary contains:
            {'url': str, 'title': str, 'snippet': str, 'raw_href': str}
        """
        if not html_content:
            logger.warning("SERP Parser: HTML content is empty. Cannot parse.")
            return []

        required_keys = ["result_item_selector", "link_selector", "title_selector", "snippet_selector"]
        if not selector_config or not all(k in selector_config for k in required_keys):
            logger.error("SERP Parser: Invalid or incomplete selector_config provided.")
            return []

        results: List[Dict[str, Optional[str]]] = []
        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            # Fetch a bit more items to account for some misses
            result_items: List[Tag] = soup.select(
                selector_config["result_item_selector"],
                limit=max_results_to_extract * 2
            )
            logger.debug(
                f"SERP Parser: Found {len(result_items)} potential result items using selector "
                f"'{selector_config['result_item_selector']}' from {serp_url}"
            )

            for item_tag in result_items:
                if len(results) >= max_results_to_extract:
                    break

                # Select raw elements
                link_element = item_tag.select_one(selector_config["link_selector"])
                title_element = item_tag.select_one(selector_config["title_selector"])
                snippet_element = item_tag.select_one(selector_config["snippet_selector"])

                raw_href: Optional[str] = None
                url: Optional[str] = None
                title: Optional[str] = None
                snippet: Optional[str] = None

                if link_element:
                    # BeautifulSoup may return an AttributeValueList or a string, so force to str
                    href_attr = link_element.get('href')
                    if isinstance(href_attr, list):
                        raw_href = href_attr[0] if href_attr else None
                    else:
                        raw_href = href_attr  # Could still be a NavigableString, so we cast below

                    if raw_href:
                        raw_href_str = str(raw_href)
                        url = normalize_url(raw_href_str, base_url=serp_url)

                if title_element:
                    title = title_element.get_text(strip=True)
                elif link_element:
                    # Fallback to link text if title_element doesn't exist or is empty
                    title = link_element.get_text(strip=True)

                if snippet_element:
                    snippet = snippet_element.get_text(separator=' ', strip=True)

                # Only accept items that have at least a URL and a title
                if url and title:
                    results.append({
                        "url": url,
                        "title": truncate_text(title, 200),
                        "snippet": truncate_text(snippet, 350) if snippet else None,
                        "raw_href": raw_href_str  # guaranteed to be a str by this point
                    })

                # Special case: image results from Google
                elif url and not title and "google.com/images" in serp_url:
                    parsed_domain = urlparse(str(raw_href_str)).netloc
                    title = f"Image result from {parsed_domain}"
                    results.append({
                        "url": url,
                        "title": truncate_text(title, 200),
                        "snippet": None,
                        "raw_href": raw_href_str
                    })

            logger.info(
                f"SERP Parser: Successfully extracted {len(results)} results "
                f"from {serp_url} (max: {max_results_to_extract})"
            )
            return results

        except Exception as e:
            logger.error(f"SERP Parser: Error parsing SERP content from {serp_url}: {e}", exc_info=True)
            return []

    @staticmethod
    def parse_google_direct_links_style(
        page_content: str,
        serp_url: str,
        max_results: int = 10
    ) -> List[Dict[str, Optional[str]]]:
        """
        Parses Google SERP results with more robust selectors for title and snippet.
        """
        results: List[Dict[str, Optional[str]]] = []
        try:
            soup = BeautifulSoup(page_content, 'lxml')
            # A more robust selector for the main result containers
            result_blocks = soup.select('div.g, div.MjjY7e, div.tF2Cxc')
            
            seen_urls = set()

            for block in result_blocks:
                if len(results) >= max_results:
                    break
                
                # Find the primary link and title element (often the same)
                link_tag = block.select_one('a[href][ping], div.yuRUbf > a, a[jsname]')
                if not link_tag:
                    continue
                
                raw_href = link_tag.get('href')
                if not raw_href or not str(raw_href).startswith("http"):
                    continue

                url = normalize_url(str(raw_href), base_url=serp_url)
                if not url or url in seen_urls:
                    continue

                parsed_href_domain = urlparse(url).netloc
                if "google.com" in parsed_href_domain:
                    continue
                
                seen_urls.add(url)

                title_text = ""
                h3_tag = block.find('h3')
                if h3_tag:
                    title_text = h3_tag.get_text(strip=True)
                else:
                    title_text = link_tag.get_text(strip=True) or parsed_href_domain

                # Improved snippet extraction
                snippet_text: Optional[str] = None
                snippet_div = block.select_one('div[data-sncf="1"], div.VwiC3b, .MUxGbd')
                if snippet_div:
                    snippet_text = snippet_div.get_text(separator=' ', strip=True)

                results.append({
                    "url": url,
                    "title": truncate_text(title_text, 200),
                    "snippet": truncate_text(snippet_text, 350) if snippet_text else "No snippet found.",
                    "raw_href": str(raw_href)
                })

            logger.info(f"SERP Parser (Robust): Extracted {len(results)} results from {serp_url}")
            return results

        except Exception as e:
            logger.error(f"SERP Parser (Robust): Error parsing content from {serp_url}: {e}", exc_info=True)
            return []

    @staticmethod
    def parse_ddg_html(
        page_content: str,
        serp_url: str,
        max_results: int = 15
    ) -> List[Dict[str, Optional[str]]]:
        """
        Parses DuckDuckGo HTML (html.duckduckgo.com) results.
        """
        results: List[Dict[str, Optional[str]]] = []
        try:
            soup = BeautifulSoup(page_content, 'lxml')
            # Selectors for html.duckduckgo.com
            # Results are in div.result
            result_blocks = soup.select('div.result, div.web-result')
            
            seen_urls = set()

            for block in result_blocks:
                if len(results) >= max_results:
                    break
                
                # Title & Link are usually in 'a.result__a'
                link_tag = block.select_one('a.result__a, h2.result__title > a')
                if not link_tag:
                    continue
                
                raw_href = link_tag.get('href')
                if not raw_href:
                    continue
                
                # DDG sometimes wraps urls in /l/?kh=...
                # But on html.duckduckgo.com it is usually direct or a distinct redirect parameter
                # The browser usually handles the final URL if we click, but here we just want the text.
                # Actually html.duckduckgo.com links are like: //duckduckgo.com/l/?kh=-1&uddg=...
                # We need to extract the real URL from 'uddg' param if present, or just use it.
                
                from urllib.parse import parse_qs, unquote
                
                url = str(raw_href)
                if "duckduckgo.com/l/" in url or "uddg=" in url:
                    parsed = urlparse(url)
                    qs = parse_qs(parsed.query)
                    if 'uddg' in qs:
                        url = qs['uddg'][0]
                
                url = normalize_url(url, base_url=serp_url)
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                title_text = link_tag.get_text(strip=True)
                
                snippet_text = None
                snippet_div = block.select_one('a.result__snippet, .result__snippet')
                if snippet_div:
                    snippet_text = snippet_div.get_text(separator=' ', strip=True)
                
                results.append({
                    "url": url,
                    "title": truncate_text(title_text, 200),
                    "snippet": truncate_text(snippet_text, 350) if snippet_text else None,
                    "raw_href": str(raw_href)
                })

            logger.info(f"SERP Parser (DDG): Extracted {len(results)} results from {serp_url}")
            return results

        except Exception as e:
            logger.error(f"SERP Parser (DDG): Error parsing content from {serp_url}: {e}", exc_info=True)
            return []