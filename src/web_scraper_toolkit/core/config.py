# ./src/web_scraper_toolkit/core/config.py
"""
Configuration Module
====================

Defines the centralized configuration structures for the toolkit using dataclasses.
Handles loading, overrides, and default values for scraper, server, and workflow settings.

Usage:
    config = ScraperConfig.load(overrides_dict)

Key Inputs:
    - overrides: Dictionary of runtime configuration overrides.

Key Outputs:
    - ScraperConfig object.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List
import pprint


@dataclass
class ScraperSettings:
    """Settings specific to the scraping engine (Playwright)."""

    headless: bool = False
    browser_type: str = "chromium"
    download_dir: Optional[str] = None
    user_agents: Optional[List[str]] = None
    launch_args: List[str] = field(default_factory=list)
    default_viewport: Dict[str, int] = field(
        default_factory=lambda: {"width": 1400, "height": 1000}
    )
    default_timeout_seconds: int = 60
    retry_attempts: int = 2


@dataclass
class MCPSettings:
    """Settings for the Model Context Protocol (MCP) Server."""

    enabled: bool = False
    transport: str = "stdio"  # Options: stdio, sse
    port: int = 8000  # Only for SSE


@dataclass
class ScraperConfig:
    """
    Centralized Configuration for WebScraperToolkit.
    """

    # Core Scraper Settings
    scraper_settings: ScraperSettings = field(default_factory=ScraperSettings)

    # MCP Server Settings
    server_settings: MCPSettings = field(default_factory=MCPSettings)

    # Workflow Settings
    workers: int = 1
    delay: float = 0.0

    # Path Settings (Resolved at runtime usually, but defaults here)
    output_dir: str = "."
    temp_dir: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __str__(self) -> str:
        return f"ScraperConfig:\n{pprint.pformat(self.to_dict())}"

    @classmethod
    def load(cls, overrides: Dict[str, Any] = None) -> "ScraperConfig":
        """
        Load configuration with optional overrides.
        """
        if overrides is None:
            overrides = {}

        # Extract nested scraper_settings if present
        scraper_settings_data = overrides.get("scraper_settings", {})

        # Create ScraperSettings instance
        scraper_settings = ScraperSettings(
            headless=scraper_settings_data.get("headless", False),
            browser_type=scraper_settings_data.get("browser_type", "chromium"),
            download_dir=scraper_settings_data.get("download_dir"),
            user_agents=scraper_settings_data.get("user_agents"),
            launch_args=scraper_settings_data.get("launch_args", []),
            default_viewport=scraper_settings_data.get(
                "default_viewport", {"width": 1400, "height": 1000}
            ),
            default_timeout_seconds=scraper_settings_data.get(
                "default_timeout_seconds", 60
            ),
            retry_attempts=scraper_settings_data.get("retry_attempts", 2),
        )

        # Extract nested server_settings if present
        server_settings_data = overrides.get("server_settings", {})
        server_settings = MCPSettings(
            enabled=server_settings_data.get("enabled", False),
            transport=server_settings_data.get("transport", "stdio"),
            port=server_settings_data.get("port", 8000),
        )

        # Create ScraperConfig instance
        config = cls(
            scraper_settings=scraper_settings,
            server_settings=server_settings,
            workers=overrides.get("workers", 1),
            delay=overrides.get("delay", 0.0),
            output_dir=overrides.get("output_dir", "."),
            temp_dir=overrides.get("temp_dir"),
        )

        return config
