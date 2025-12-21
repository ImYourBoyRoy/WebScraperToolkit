# ./src/web_scraper_toolkit/crawler/engine.py
"""
Proxie Crawler Engine
=====================

The main autonomous crawling loop.
Integrates:
-   Proxie (Fetching & Rotation)
-   Playbook (Rules & Policies)
-   SitemapHandler (Seeding)
-   Frontier (Queue)
"""

import asyncio
import logging
import re
from typing import List, Optional, Any, Dict, Tuple
from bs4 import BeautifulSoup
import json

from ..proxie import ProxyManager
from ..scraper import ProxyScraper
from ..browser.playwright_handler import PlaywrightManager
from ..browser.config import BrowserConfig
from ..playbook.models import Playbook
from ..parsers.sitemap import parse_sitemap_urls
from .frontier import Frontier
from .politeness import PolitenessManager
from .state import StateManager

from .config import CrawlerConfig

logger = logging.getLogger(__name__)


class AutonomousCrawler:
    def __init__(
        self,
        playbook: Playbook,
        proxy_manager: Optional[ProxyManager] = None,
        config: CrawlerConfig = None,
        state_file: str = "crawl_state.json",
    ):
        self.playbook = playbook
        self.proxy_manager = proxy_manager  # Optional
        self.config = config or CrawlerConfig()

        # Initialize PlaywrightManager (Dynamic Engine)
        # We pass the proxy_manager to it so it handles rotation internally
        browser_cfg = BrowserConfig(
            headless=True,  # Default to headless for autonomous, smart_fetch switches if needed
            browser_type="chromium",  # Default for best stealth
            user_agent=playbook.settings.user_agent,
        )
        self.browser_manager = PlaywrightManager(
            config=browser_cfg, proxy_manager=self.proxy_manager
        )

        # Fast Lane (aiohttp) - Optional
        # We use this for speed and only fall back to browser if needed
        self.fast_scraper = ProxyScraper(manager=self.proxy_manager)

        self.frontier = Frontier()
        self.state = StateManager(state_file)

        # Politeness Logic: Global Config overrides Playbook
        respect = playbook.settings.respect_robots
        if self.config.global_ignore_robots:
            respect = False

        self.politeness = PolitenessManager(
            user_agent=playbook.settings.user_agent or self.config.default_user_agent,
            respect_robots=respect,
        )

        self.results = []  # In-memory storage
        self.results_filename = f"results_{self.playbook.name.replace(' ', '_')}.jsonl"

        # Rule Optimization
        self._successful_rules = []  # Cache of rules that worked recently

    async def initialize(self):
        """Prepares the crawler: starts browser, loads state, seeds frontier."""
        await self.browser_manager.start()
        self.state.load()

        # Seed from Playbook
        for url in self.playbook.base_urls:
            if "sitemap" in url or url.endswith(".xml"):
                await self._process_sitemap(url)
            else:
                if not self.state.is_seen(url):
                    await self.frontier.add_url(url, depth=0)

    async def _process_sitemap(self, url: str):
        """Fetches and extracts URLs from a sitemap."""
        logger.info(f"Seeding from Sitemap: {url}")
        # Use Smart Fetch (even for XML, it handles potential cloudflare better)
        content, _, status = await self.browser_manager.smart_fetch(url)
        if content and status == 200:
            urls = parse_sitemap_urls(content)
            count = 0
            for u in urls:
                if not self.state.is_seen(u):
                    await self.frontier.add_url(u, depth=0)
                    count += 1
            logger.info(f"Seeded {count} URLs from sitemap.")

    async def run(self):
        """Main Crawl Loop."""
        logger.info(f"Starting Crawl: {self.playbook.name}")
        await self.initialize()

        # Simple worker pool (future: true async Task pool)
        # For now, simplistic loop
        while not self.frontier.is_empty():
            item = await self.frontier.get_next()
            if not item:
                break

            url = item.url
            if self.state.is_seen(url):
                continue

            # Politeness Check
            if not await self.politeness.can_fetch(url):
                logger.warning(f"Politeness Blocked: {url}")
                continue

            # Delay
            await asyncio.sleep(self.playbook.settings.crawl_delay)

            await self._process_url(url, item.depth)

            # Save State periodically?
            self.state.add_seen(url)
            if len(self.state.seen) % 10 == 0:
                self.state.save()

        self.state.save()
        await self.browser_manager.stop()
        logger.info(f"Crawl Complete. Processed {len(self.results)} items.")

    async def _process_url(self, url: str, depth: int):
        logger.info(f"Crawling: {url}")

        # Hybrid Fetch Strategy
        # 1. Try Fast Lane (aiohttp)
        # 2. If blocked/JS-needed, Try Power Lane (Playwright)
        content = None
        status = None

        # Attempt Fast Lane
        try:
            fast_content = await self.fast_scraper.secure_fetch(url)
            if fast_content:
                content = fast_content
                status = 200  # Assumed if content returned
                logger.info(f"Fast Lane Success: {url}")
        except Exception:
            pass  # Fallback

        # Fallback to Power Lane
        if not content:
            logger.info(f"Switching to Power Lane (Playwright) for {url}")
            content, final_url, status = await self.browser_manager.smart_fetch(url)

        if not content or status not in [200, 404]:  # Keep 404 handling logic separate?
            # If strictly failed fetch
            if status in [403, 429, 503]:
                logger.warning(f"Blocked or Failed ({status}): {url}")
            return

        # Simple WP API Check
        if "wp-json" in content and depth == 0:
            # Heuristic: if we see wp-json in source, maybe try to discover endpoints?
            # For now, strict Rules only.
            pass

        soup = BeautifulSoup(content, "lxml")

        # 1. Apply Extraction Rules
        extracted_data = {}
        validation_errors = []

        # Optimization: Try recently successful rules first if 'reuse_rules' is enabled
        rules_to_try = self.playbook.rules
        if self.playbook.settings.reuse_rules:
            # Prioritize successful rules, then the rest (deduplicated)
            rules_to_try = self._successful_rules + [
                r for r in self.playbook.rules if r not in self._successful_rules
            ]

        for rule in rules_to_try:
            if rule.type == "extract":
                if self._matches(url, rule):
                    # Extract Data
                    for field in rule.extract_fields:
                        val = self._extract_field(soup, field)
                        if val:
                            extracted_data[field.name] = val

                    # If successful match, promote rule
                    if (
                        extracted_data
                        and self.playbook.settings.reuse_rules
                        and rule not in self._successful_rules
                    ):
                        self._successful_rules.insert(0, rule)
                        if len(self._successful_rules) > 10:  # Limit cache
                            self._successful_rules.pop()

        # 5. Validation (AI Feedback Loop)
        if self.playbook.settings.validation_enabled and extracted_data:
            valid, errors = self._validate_data(extracted_data)
            if not valid:
                validation_errors = errors
                logger.warning(f"Validation failed for {url}: {errors}")
                # If AI Context is enabled, we could trigger a callback or store error for the agent
                if self.playbook.settings.ai_context:
                    extracted_data["_ai_feedback"] = (
                        f"Validation Errors: {errors}. Please refine playbook."
                    )

        if extracted_data:
            result_entry = {
                "url": url,
                "data": extracted_data,
                "timestamp": "iso-now",
                "validation_errors": validation_errors,
            }
            self.results.append(result_entry)

            # Persist to disk
            try:
                with open(self.results_filename, "a", encoding="utf-8") as f:
                    f.write(json.dumps(result_entry) + "\n")
            except Exception as e:
                logger.error(f"Failed to write result to disk: {e}")

            logger.info(f"Extracted: {extracted_data}")

        # 2. Apply Traversal Rules (if depth allows)
        if depth < self.playbook.settings.max_depth:
            for rule in self.playbook.rules:
                if rule.type == "follow":
                    # If global follow rule (no regex) or matches
                    links = self._extract_links(soup)
                    for link in links:
                        if self._matches(link, rule):
                            await self.frontier.add_url(link, depth + 1)

                # Logic to hit API endpoint
                api_url = url.rstrip("/") + "/wp-json/wp/v2/posts"
                logger.info(f"Checking WP API: {api_url}")
                try:
                    api_content, _, api_status = await self.browser_manager.smart_fetch(
                        api_url
                    )
                    if api_content and api_status == 200:
                        posts = json.loads(api_content)
                        if isinstance(posts, list):
                            for post in posts:
                                link = post.get("link")
                                if link and not self.state.is_seen(link):
                                    logger.info(f"Discovered via WP API: {link}")
                                    await self.frontier.add_url(link, depth + 1)
                except Exception as e:
                    logger.warning(f"WP API Discovery failed for {url}: {e}")

    def _matches(self, text: str, rule: Any) -> bool:
        if not rule.regex:
            return True  # If no regex, match all? Or match none?
            # Usually 'follow' without regex means follow everything
        return bool(re.search(rule.regex, text))

    def _extract_links(self, soup) -> List[str]:
        return [
            a["href"]
            for a in soup.find_all("a", href=True)
            if a["href"].startswith("http")
        ]

    def _extract_field(self, soup, field) -> Optional[str]:
        if field.type == "css":
            el = soup.select_one(field.selector)
            if el:
                return (
                    el.get(field.attribute)
                    if field.attribute
                    else el.get_text(strip=True)
                )
        return None

    def _validate_data(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Basic schema validation.
        In strict mode, checks for None/Empty values if explicitly required.
        """
        errors = []
        for key, value in data.items():
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"Missing required field: {key}")
        return len(errors) == 0, errors
