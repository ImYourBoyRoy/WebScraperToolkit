# ./src/web_scraper_toolkit/playbook/models.py
"""
Playbook Models
===============

Defines the structure of a Scraping Playbook using Pydantic.
Controls how the Crawler behaves: rules, extraction, and settings.

Compatible with Pydantic v2 and forward-compatible with v3.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict

# --- Enums & Literals ---
RuleType = Literal["follow", "extract", "wp_api_discover", "sitemap"]
ExtractorType = Literal["css", "xpath", "regex", "json"]


# --- Settings ---
class PlaybookSettings(BaseModel):
    """Configuration for the crawler's behavior."""

    model_config = ConfigDict(extra="ignore")

    respect_robots: bool = Field(True, description="Respect robots.txt rules.")
    user_agent: Optional[str] = Field(None, description="Custom User-Agent string.")
    max_depth: int = Field(3, description="Maximum crawl depth from start URLs.")
    max_pages: int = Field(100, description="Maximum number of pages to visit.")
    crawl_delay: float = Field(1.0, description="Delay between requests (seconds).")

    # AI & Adaptive Features
    ai_context: bool = Field(False, description="Enable AI-aware extraction/feedback.")
    validation_enabled: bool = Field(
        False, description="Enable schema validation of extracted data."
    )
    reuse_rules: bool = Field(
        True, description="Cache and reuse rules discovered from sitemaps."
    )


# --- Extractors ---
class FieldExtractor(BaseModel):
    """Defines how to extract a single field from a page."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="The name of the field being extracted.")
    extractor_type: ExtractorType = Field("css", description="The extraction method.")
    selector: str = Field(
        ..., description="The selector (CSS, XPath) or regex pattern."
    )
    is_list: bool = Field(False, description="If True, extract all matches as a list.")


# --- Rules ---
class Rule(BaseModel):
    """
    A single rule that the crawler evaluates on each page.
    Can be a 'follow' link rule or an 'extract' data rule.
    """

    model_config = ConfigDict(extra="ignore")

    rule_type: RuleType = Field(..., description="The type of rule.")
    name: Optional[str] = Field(None, description="An identifier for this rule.")
    url_pattern: Optional[str] = Field(
        None, description="A regex pattern to match against URLs."
    )
    selector: Optional[str] = Field(
        None, description="A CSS/XPath selector for 'follow' rules."
    )
    extract_fields: List[FieldExtractor] = Field(
        default_factory=list, description="Fields to extract if URL matches."
    )
    callback: Optional[str] = Field(
        None, description="Optional name of a custom callback function."
    )


# --- The Playbook ---
class Playbook(BaseModel):
    """
    The Master Plan.
    Defines where to start, how to move, and what to take.
    """

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Name of this playbook.")
    base_urls: List[str] = Field(
        ..., description="Starting points. Can be URLs, Sitemaps, or API roots."
    )

    rules: List[Rule] = Field(
        default_factory=list, description="List of traversal and extraction rules."
    )
    settings: PlaybookSettings = Field(
        default_factory=PlaybookSettings, description="Crawler settings."
    )
