# ./src/web_scraper_toolkit/playbook/config.py
"""
Playbook Configuration
======================

Global defaults for Playbook generation and execution.
"""

from dataclasses import dataclass, asdict


@dataclass
class PlaybookGlobalConfig:
    default_crawl_delay: float = 1.0
    default_max_depth: int = 2
    default_respect_robots: bool = True

    def to_dict(self) -> dict:
        return asdict(self)
