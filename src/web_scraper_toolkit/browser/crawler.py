# ./src/web_scraper_toolkit/browser/crawler.py
"""
Web Crawler Engine
==================

The core orchestration engine for processing URLs.
Manages concurrency, rate limiting, and output dispatching.

Usage:
    crawler = WebCrawler(config=sc_config)
    await crawler.run(urls=["..."], output_format="markdown")

Key Features:
    - Async/Await concurrency with Semaphore.
    - Smart Retries (Headless -> Headed fallback).
    - Batch processing with progress tracking.
"""

import asyncio
import os
import logging
import csv
import json
from typing import List, Optional, Dict, Any, Tuple, Union
import requests

# Import toolkit components
from .playwright_handler import PlaywrightManager
from ..parsers.scraping_tools import (
    read_website_markdown,
    read_website_content,
    extract_metadata,
)
from ..core.config import ScraperConfig
from ..core.file_utils import (
    ensure_directory,
    generate_safe_filename,
    get_unique_filepath,
    merge_content_files,
)
from ..parsers.sitemap_handler import extract_sitemap_tree, parse_sitemap_urls

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
                resp = requests.get(input_source, timeout=10)
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


class WebCrawler:
    def __init__(
        self,
        config: Union[Dict[str, Any], ScraperConfig] = None,
        workers: int = 1,
        delay: float = 0.0,
    ):
        # Handle dict vs ScraperConfig for backward compatibility
        if hasattr(config, "to_dict"):
            self.config = config
        else:
            self.config = ScraperConfig.load(config)

        self.workers = workers  # Override config workers if provided explicitly?
        # Ideally config has workers. But let's keep arguments for now or sync them.
        self.config.workers = workers or self.config.workers
        self.config.delay = delay or self.config.delay

        self.delay = self.config.delay
        self.semaphore = asyncio.Semaphore(self.config.workers)

    async def process_single_url(
        self,
        index: int,
        total: int,
        url: str,
        output_format: str,
        export: bool,
        merge: bool,
        output_dir: str,
        output_filename: str = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Process a single URL: fetch, convert/screenshot, save."""
        async with self.semaphore:
            # Rate limit delay before starting (politeness)
            if self.delay > 0:
                await asyncio.sleep(self.delay)

            print(f"[{index + 1}/{total}] Processing: {url}")
            content = None
            output_file = None

            # Retry Loop for Smart Fallback (Headless -> Headed)
            max_attempts = 2

            for attempt in range(max_attempts):
                try:
                    # Current Config check
                    is_headless = self.config.scraper_settings.headless
                    if attempt > 0:
                        print(
                            f"  -> Retry Attempt {attempt + 1} (Headless: {is_headless})..."
                        )

                    # Generate Output Filename using FileUtils
                    # Extension logic
                    ext = "txt"
                    if output_format == "markdown":
                        ext = "md"
                    elif output_format == "html":
                        ext = "html"
                    elif output_format == "screenshot":
                        ext = "png"
                    elif output_format == "pdf":
                        ext = "pdf"

                    if export or output_format in ["screenshot", "pdf"]:
                        # We determine the filename early for export modes
                        # If output_filename is provided (Single Mode), use it.
                        # Else generate safe unique name.
                        output_file = generate_safe_filename(
                            url, output_dir, ext, specific_name=output_filename
                        )

                    # Status tracking
                    status_code = 0
                    success = False

                    # --- DISPATCHER ---
                    if output_format == "markdown":
                        # Convert config to dict for legacy tools if needed, OR update tools to accept obj
                        # Currently scraping_tools expects dict.
                        content = await asyncio.to_thread(
                            read_website_markdown, url, config=self.config.to_dict()
                        )
                        if content:
                            success = True

                    elif output_format == "text":
                        content = await asyncio.to_thread(
                            read_website_content, url, config=self.config.to_dict()
                        )
                        if content:
                            success = True

                    elif output_format == "html":
                        # PlaywrightManager now accepts ScraperConfig object
                        manager = PlaywrightManager(config=self.config)
                        async with manager:
                            c, _, s = await manager.smart_fetch(url)
                            status_code = s
                            if s == 200:
                                content = c
                                success = True
                            else:
                                logger.error(f"Fetch failed {s}")

                    elif output_format == "metadata":
                        content = await asyncio.to_thread(
                            extract_metadata, url, config=self.config.to_dict()
                        )
                        if content:
                            success = True

                    elif output_format == "screenshot":
                        manager = PlaywrightManager(config=self.config)
                        async with manager:
                            success, status_code = await manager.capture_screenshot(
                                url, output_file
                            )

                    elif output_format == "pdf":
                        manager = PlaywrightManager(config=self.config)
                        async with manager:
                            success, status_code = await manager.save_pdf(
                                url, output_file
                            )

                    # --- SMART FALLBACK CHECK ---
                    # If failed with 403/429/0 (Blocked) AND we are Headless, try switching to Headed
                    blocked_codes = [
                        403,
                        429,
                        0,
                    ]  # 0 often means network error/timeout/blocked
                    if not success and (status_code in blocked_codes) and is_headless:
                        logger.warning(
                            f"Request blocked (Status: {status_code}) in Headless mode. Switching to Visible mode for retry..."
                        )

                        # Update config for next iteration
                        self.config.scraper_settings.headless = False

                        # Continue to next attempt
                        continue

                    # Individual Export (Content Based)
                    if content and export and not merge:
                        # Output file was already determined above
                        with open(output_file, "w", encoding="utf-8") as f:
                            f.write(content)
                        print(f"  -> Saved {output_file}")

                    # Print to stdout if not exporting and not merging
                    if content and not export and not merge:
                        print("\n--- Content Start ---")
                        print(content)
                        print("--- Content End ---\n")

                    if (
                        output_file
                        and success
                        and (output_format in ["screenshot", "pdf"])
                    ):
                        print(f"  -> Saved {output_file}")

                    # If success or we ran out of retries, return
                    return content, output_file if success else None

                except Exception as e:
                    logger.error(f"Error extracting {url} (Attempt {attempt + 1}): {e}")
                    # If critical error, maybe don't retry? Or retry?
                    # Let's retry on attempt 1 just in case

            return None, None

    async def run(
        self,
        urls: List[str],
        output_format: str,
        export: bool = False,
        merge: bool = False,
        output_dir: str = ".",
        temp_dir: str = None,
        clean: bool = False,
        output_filename: str = None,
    ):
        """Run the crawler on the list of URLs."""
        if not urls:
            return

        # Directory Logic
        # Intermediates go to temp_dir (if set) or output_dir.
        working_dir = temp_dir if temp_dir else output_dir

        # Ensure directories exist
        ensure_directory(working_dir)
        ensure_directory(output_dir)

        self.failed_urls = []  # Reset failures

        if len(urls) == 1:
            print(f"\n--- Starting Single Target Scrape: {urls[0]} ---")
        else:
            print(f"\n--- Starting Batch Scrape: {len(urls)} targets ---")

        print(f"Format: {output_format.upper()}")
        print(f"Intermediate Dir: {working_dir} | Output Dir: {output_dir}")
        print(f"Concurrency: {self.workers} workers, {self.delay}s delay")

        tasks = []
        for i, url in enumerate(urls):
            # Pass working_dir where individual files should be saved
            # Only use specific output_filename if processing a single URL
            single_file_name = output_filename if len(urls) == 1 else None
            tasks.append(
                self.process_single_url(
                    i,
                    len(urls),
                    url,
                    output_format,
                    export,
                    merge,
                    working_dir,
                    output_filename=single_file_name,
                )
            )

        results = await asyncio.gather(*tasks)

        # Process results
        collected_outputs = []
        collected_files = []

        for i, res in enumerate(results):
            content, outfile = res
            if content:
                collected_outputs.append(content)
            if outfile:
                collected_files.append(outfile)

            # If both are None, it failed
            if not content and not outfile:
                self.failed_urls.append(urls[i])

        # --- MERGE STEP ---
        if merge:
            print("\n--- Merging Outputs ---")

            ext = "md" if output_format == "markdown" else "txt"
            if output_format == "pdf":
                ext = "pdf"

            # Determine base filename
            target_name = output_filename if output_filename else f"merged_output.{ext}"

            # Ensure it has correct extension if auto-defaulting,
            # but if user provided specific name, respect it or append ext?
            # User said "filename-1.pdf", so let's respect user input but ensure uniqueness.

            # Generate unique path
            final_output_path = get_unique_filepath(
                os.path.join(output_dir, target_name)
            )

            if output_format == "pdf":
                if collected_files:
                    merge_content_files(collected_files, "pdf", final_output_path)
            elif output_format in ["markdown", "text", "metadata", "html"]:
                if collected_outputs:
                    merge_content_files(
                        collected_outputs, output_format, final_output_path
                    )

            if os.path.exists(final_output_path):
                print(f"Merged Output Created: {final_output_path}")

        # --- CLEANUP STEP ---
        if merge and clean and collected_files:
            print(f"\n--- Cleaning up {len(collected_files)} intermediate files ---")
            for f in collected_files:
                try:
                    if os.path.exists(f):
                        os.remove(f)
                        print(f"Deleted: {os.path.basename(f)}")
                except Exception as e:
                    logger.error(f"Failed to delete {f}: {e}")

        # --- FAILURE REPORT ---
        if self.failed_urls:
            print(f"\n--- ⚠️  Failures: {len(self.failed_urls)} ---")
            for f in self.failed_urls:
                print(f"  [x] {f}")

        print("\nDone.")
