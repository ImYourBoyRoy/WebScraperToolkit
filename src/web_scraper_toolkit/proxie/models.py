# ./src/web_scraper_toolkit/proxie/models.py
"""
Models for the Proxie tool.

This module defines the strictly typed data structures used for proxy management.
"""

from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional


class ProxyProtocol(Enum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS4 = "socks4"
    SOCKS5 = "socks5"


class ProxyStatus(Enum):
    ACTIVE = auto()  # Valid and ready to use
    DEAD = auto()  # Connection refused or timeout
    COOLDOWN = auto()  # Temporarily blocked (403, 429)
    DENIED = auto()  # Authentication failed
    LEAKING = auto()  # FATAL: Leaking real IP (Kill-Switch triggered)
    UNTESTED = auto()  # Loaded but not yet validated


@dataclass
class Proxy:
    hostname: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: ProxyProtocol = ProxyProtocol.SOCKS5

    status: ProxyStatus = ProxyStatus.UNTESTED
    health_score: float = 100.0  # 0.0 to 100.0

    total_calls: int = 0
    failed_calls: int = 0
    last_used_ts: float = 0.0

    @property
    def url(self) -> str:
        """Constructs the proxy URL for aiohttp/requests."""
        auth = ""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"
        return f"{self.protocol.value}://{auth}{self.hostname}:{self.port}"

    def __str__(self):
        return f"{self.protocol.value}://{self.hostname}:{self.port}"
