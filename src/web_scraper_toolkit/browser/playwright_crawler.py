# ./src/web_scraper_toolkit/browser/playwright_crawler.py
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
from typing import List, Optional, Tuple

# Import toolkit components
from .playwright_handler import PlaywrightManager
from ..parsers.scraping_tools import (
    read_website_markdown,
    read_website_content,
    extract_metadata,
)
from .config import BrowserConfig
from ..core.file_utils import (
    ensure_directory,
    generate_safe_filename,
    get_unique_filepath,
    merge_content_files,
)
from ..parsers.extraction.contacts import (
    extract_emails,
    extract_phones,
    extract_socials,
    extract_heuristic_names,
)

logger = logging.getLogger(__name__)


class WebCrawler:
    def __init__(
        self,
        config: Optional[BrowserConfig] = None,
        workers: int = 1,
        delay: float = 0.0,
    ):
        self.config = config or BrowserConfig()
        self.workers = workers
        self.delay = delay
        self.semaphore = asyncio.Semaphore(self.workers)

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
        extract_contacts: bool = False,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Process a single URL: fetch, convert/screenshot, save."""
        async with self.semaphore:
            # Rate limit delay before starting (politeness)
            if self.delay > 0:
                await asyncio.sleep(self.delay)

            logger.info(f"[{index + 1}/{total}] Processing: {url}")
            content = None
            output_file = None

            # Retry Loop for Smart Fallback (Headless -> Headed)
            max_attempts = 2

            for attempt in range(max_attempts):
                try:
                    # Current Config check
                    is_headless = self.config.scraper_settings.headless
                    if attempt > 0:
                        logger.warning(
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
                    raw_html_for_contacts = None  # We might need this for contacts

                    # --- DISPATCHER ---
                    if output_format == "markdown":
                        # Convert config to dict for legacy tools if needed
                        content = await asyncio.to_thread(
                            read_website_markdown, url, config=self.config
                        )
                        if content:
                            success = True
                            # If we need contacts, we might need raw HTML or just use the markdown?
                            # Actually contacts parser needs HTML for regex (hidden emails) and Soup for socials.
                            # read_website_markdown converts HTML -> MD.
                            # We should probably fetch HTML specifically if contacts are requested.
                            # Optimization: read_website_markdown does a fetch. We don't want to double fetch.
                            # But read_website_markdown encapsulates the browser/requests logic.
                            # For "Autonomous" robust behavior, we accept the double-fetch cost OR we need to refactor read_markdown to return raw too.
                            # Let's double fetch for now to keep it safe, but maybe use 'read_website_content' which is cheaper?
                            pass

                    elif output_format == "text":
                        content = await asyncio.to_thread(
                            read_website_content, url, config=self.config
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
                                raw_html_for_contacts = c
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

                    # --- AUTONOMOUS CONTACT EXTRACTION ---
                    # If success and flag is set, attempt to extract contacts
                    if success and extract_contacts and content:
                        try:
                            # We need HTML for this. If we have it (html mode), great.
                            # If not, we fetch it (cheaply via requests/read_website_content if possible)
                            # Or we use what we have? Markdown/Text is bad for HTML regex.

                            c_html = raw_html_for_contacts
                            if not c_html:
                                # Quick fetch for parsing
                                c_html = await asyncio.to_thread(
                                    read_website_content,
                                    url,
                                    config=self.config,
                                )

                            if c_html:
                                from bs4 import BeautifulSoup

                                soup = BeautifulSoup(c_html, "lxml")
                                c_text = soup.get_text(separator=" ", strip=True)

                                emails = extract_emails(c_html, url)
                                phones = extract_phones(c_text, url)
                                socials = extract_socials(soup, url)
                                names = extract_heuristic_names(soup)

                                if emails or phones or socials or names:
                                    logger.info(
                                        f"  -> Found Contacts: {len(emails)} emails, {len(phones)} phones, {len(socials)} socials"
                                    )
                                    if names:
                                        logger.info(f"  -> Identified: {names}")

                                    # Append to content (Autonomous blending)
                                    # We add a nice footer section
                                    contact_section = (
                                        "\n\n---\n### Extracted Contacts\n"
                                    )

                                    if names:
                                        contact_section += "**Identity**\n"
                                        for k, v in names.items():
                                            contact_section += f"- {k.replace('_', ' ').title()}: {v}\n"
                                        contact_section += "\n"

                                    if emails:
                                        contact_section += (
                                            "**Emails**\n"
                                            + "\n".join(
                                                [f"- {e['value']}" for e in emails]
                                            )
                                            + "\n"
                                        )
                                    if phones:
                                        contact_section += (
                                            "**Phones**\n"
                                            + "\n".join(
                                                [f"- {p['value']}" for p in phones]
                                            )
                                            + "\n"
                                        )
                                    if socials:
                                        contact_section += (
                                            "**Socials**\n"
                                            + "\n".join(
                                                [
                                                    f"- [{s['type']}]({s['url']})"
                                                    for s in socials
                                                ]
                                            )
                                            + "\n"
                                        )

                                    if (
                                        output_format == "markdown"
                                        or output_format == "text"
                                    ):
                                        content += contact_section
                                    # For HTML/PDF/JSON we might need different handling, but appending to MD/Text checks the box.
                        except Exception as ce:
                            logger.warning(f"Contact extraction failed for {url}: {ce}")

                    # Individual Export (Content Based)
                    if content and export and not merge:
                        # Output file was already determined above
                        with open(output_file, "w", encoding="utf-8") as f:
                            f.write(content)
                        logger.info(f"  -> Saved {output_file}")

                    # Print to stdout if not exporting and not merging
                    if content and not export and not merge:
                        # We log sample content instead of printing whole thing to avoid clutter
                        sample = (
                            content[:200].replace("\n", " ") + "..."
                            if len(content) > 200
                            else content
                        )
                        logger.debug(f"Content Sample: {sample}")

                    if (
                        output_file
                        and success
                        and (output_format in ["screenshot", "pdf"])
                    ):
                        logger.info(f"  -> Saved {output_file}")

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
        extract_contacts: bool = False,
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
            logger.info(f"--- Starting Single Target Scrape: {urls[0]} ---")
        else:
            logger.info(f"--- Starting Batch Scrape: {len(urls)} targets ---")

        logger.info(f"Format: {output_format.upper()}")
        logger.info(f"Intermediate Dir: {working_dir} | Output Dir: {output_dir}")
        logger.info(f"Concurrency: {self.workers} workers, {self.delay}s delay")

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
                    extract_contacts=extract_contacts,
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
            logger.info("--- Merging Outputs ---")

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
                logger.info(f"Merged Output Created: {final_output_path}")

        # --- CLEANUP STEP ---
        if merge and clean and collected_files:
            logger.info(
                f"--- Cleaning up {len(collected_files)} intermediate files ---"
            )
            for f in collected_files:
                try:
                    if os.path.exists(f):
                        os.remove(f)
                        logger.info(f"Deleted: {os.path.basename(f)}")
                except Exception as e:
                    logger.error(f"Failed to delete {f}: {e}")

        # --- FAILURE REPORT ---
        if self.failed_urls:
            logger.error(f"--- ⚠️  Failures: {len(self.failed_urls)} ---")
            for f in self.failed_urls:
                logger.error(f"  [x] {f}")

        logger.info("Done.")
        return results
