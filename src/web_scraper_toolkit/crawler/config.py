# ./src/web_scraper_toolkit/crawler/config.py
"""
Crawler Configuration
=====================

Global defaults for the Autonomous Crawler.
Can be overridden by Playbook settings.
"""

from dataclasses import dataclass, asdict


@dataclass
class CrawlerConfig:
    """
    Global configuration for the Crawler.
    """

    # Identification
    default_user_agent: str = "WebScraperToolkit/1.0 (Crawler)"

    # Limits
    default_max_depth: int = 3
    default_max_pages: int = 100
    default_crawl_delay: float = 1.0

    # Politeness
    global_ignore_robots: bool = False  # If True, overrides Playbook's respect_robots

    # Timeouts
    request_timeout: int = 30

    def to_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:
        return (
            f"CrawlerConfig(\n"
            f"  User-Agent: {self.default_user_agent}\n"
            f"  Max Depth: {self.default_max_depth}\n"
            f"  Max Pages: {self.default_max_pages}\n"
            f"  Crawl Delay: {self.default_crawl_delay}s\n"
            f"  Global Ignore Robots: {self.global_ignore_robots}\n"
            f")"
        )
