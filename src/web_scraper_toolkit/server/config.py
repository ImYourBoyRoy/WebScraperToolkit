# ./src/web_scraper_toolkit/server/config.py
"""
Server Configuration
====================

Settings for the MCP Server.
"""

from dataclasses import dataclass, asdict


@dataclass
class ServerConfig:
    name: str = "Web Scraper Toolkit"
    version: str = "0.1.7"
    port: int = 8000
    host: str = "localhost"
    log_level: str = "INFO"

    def to_dict(self) -> dict:
        return asdict(self)
