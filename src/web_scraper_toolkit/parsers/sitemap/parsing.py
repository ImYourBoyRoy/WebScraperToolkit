# ./src/web_scraper_toolkit/parsers/sitemap/parsing.py
"""
Sitemap Parsing
===============

Logic for parsing raw sitemap content (XML/Text).
"""

import re
from typing import List


def parse_sitemap_urls(content: str) -> List[str]:
    """
    Extract URLs from sitemap XML using robust regex.
    Handles standard <loc> tags and CDATA.
    """
    # Regex to capture content inside <loc>...</loc>, ignoring namespace prefixes
    # and handling potential CDATA usage.

    # This non-greedy match finds content within loc OR link tags (for RSS sitemaps)
    raw_matches = re.findall(
        r"(?:<|&lt;)(?:[\w]+:)?(?:loc|link)(?:>|&gt;)(.*?)(?:<|&lt;)/(?:[\w]+:)?(?:loc|link)(?:>|&gt;)",
        content,
        re.IGNORECASE | re.DOTALL,
    )

    cleaned_urls = []
    for raw in raw_matches:
        cleaned = raw.strip()

        # Robustly remove CDATA wrapper if present (case insensitive)
        if "<![CDATA[" in cleaned.upper():
            # Use regex for case-insensitive replacement to be safe
            cleaned = re.sub(r"<!\[CDATA\[", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\]\]>", "", cleaned, flags=re.IGNORECASE)

        cleaned_urls.append(cleaned.strip())

    return [u for u in cleaned_urls if u]
