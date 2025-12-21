# ./src/web_scraper_toolkit/parsers/config.py
"""
Parser Configuration
====================

Settings for various parsers (markdown, metadata, etc).
"""

from dataclasses import dataclass, asdict


@dataclass
class ParserConfig:
    # Markdown conversion settings
    ignore_links: bool = False
    ignore_images: bool = False
    body_width: int = 0  # 0 = infinite/no wrap

    # Metadata extraction
    extract_opengraph: bool = True
    extract_twitter_cards: bool = True

    def to_dict(self) -> dict:
        return asdict(self)
