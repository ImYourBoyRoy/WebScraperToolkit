# ./src/web_scraper_toolkit/core/input.py
"""
Input Parser
============

Utilities for parsing input sources (files, URLs, sitemaps) into a list of URLs.
"""

import os
import csv
import json
import logging
import requests
from typing import List

from ..parsers.sitemap import extract_sitemap_tree, parse_sitemap_urls

logger = logging.getLogger(__name__)


async def load_urls_from_source(input_source: str) -> List[str]:
    """
    Load URLs from a local file OR a remote Sitemap.
    Strictly rejects generic remote Webpages (use --url for those).
    """
    urls = []

    # 1. Remote Source
    if input_source.startswith("http"):
        # Check for explicitly supported remote formats
        is_sitemap = "sitemap" in input_source.lower() or input_source.endswith(".xml")
        is_data = input_source.endswith((".json", ".csv", ".txt"))

        if is_sitemap:
            logger.info(f"Fetching remote sitemap: {input_source}")
            return await extract_sitemap_tree(input_source)
        elif is_data:
            # Fetch simple data files
            try:
                import asyncio

                resp = await asyncio.to_thread(requests.get, input_source, timeout=10)
                resp.raise_for_status()
                content_text = resp.text
                ext = os.path.splitext(input_source)[1].lower()
                # Parse using local logic below (pass to next block)
            except Exception as e:
                logger.error(f"Failed to fetch remote data file: {e}")
                return []
        else:
            logger.error(
                f"Input '{input_source}' does not look like a file or sitemap. Use --url for single web pages."
            )
            return []

    else:
        # 2. Local File
        if not os.path.exists(input_source):
            logger.error(f"Input file not found: {input_source}")
            return []
        try:
            with open(input_source, "r", encoding="utf-8") as f:
                content_text = f.read()
            ext = os.path.splitext(input_source)[1].lower()
        except Exception as e:
            logger.error(f"Failed to read local file: {e}")
            return []

    # 3. Parse Content (Local or Remote Data)
    try:
        if ext == ".txt" or ext not in [".csv", ".json", ".xml"]:
            lines = content_text.splitlines()
            valid = []
            for line in lines:
                cleaned_line = line.strip().strip(",").strip('"').strip("'")
                if cleaned_line.lower().startswith(("http://", "https://", "www.")):
                    valid.append(cleaned_line)
            urls.extend(valid)

        elif ext == ".csv":
            from io import StringIO

            f = StringIO(content_text)
            reader = csv.reader(f)
            for row in reader:
                for cell in row:
                    if cell.strip().startswith("http"):
                        urls.append(cell.strip())
                        break

        elif ext == ".json":
            data = json.loads(content_text)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        urls.append(item)
                    elif isinstance(item, dict) and "url" in item:
                        urls.append(item["url"])

        elif ext == ".xml":
            # Use handler logic even for local XML
            urls.extend(parse_sitemap_urls(content_text))

    except Exception as e:
        logger.error(f"Error parsing content: {e}")

    return urls
