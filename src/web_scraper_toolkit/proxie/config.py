# ./src/web_scraper_toolkit/proxie/config.py
"""
Configuration for the Proxie tool.

This module handles the configuration logic, defaults, and validation for proxy management.
It supports loading from a dictionary (dynamic) or falling back to defaults.
"""

from dataclasses import dataclass


@dataclass
class ProxieConfig:
    """
    Configuration object for the Proxie tool.
    """

    # Validation Targets
    validation_url: str = "https://httpbin.org/ip"
    timeout_seconds: int = 10

    # Manager Settings
    max_concurrent_checks: int = 50  # Speed of validation
    rotation_strategy: str = "round_robin"  # or 'random', 'health_weighted'

    # Kill-Switch
    enforce_secure_ip: bool = True  # If True, stops if Real IP is detected

    # Retry Logic
    max_retries: int = 3
    cooldown_seconds: int = 300  # Time to wait before retrying a 'COOLDOWN' proxy

    @classmethod
    def from_dict(cls, data: dict) -> "ProxieConfig":
        """Creates a config object from a dictionary, using defaults for missing keys."""
        return cls(
            validation_url=data.get("validation_url", "https://httpbin.org/ip"),
            timeout_seconds=int(data.get("timeout_seconds", 10)),
            max_concurrent_checks=int(data.get("max_concurrent_checks", 50)),
            rotation_strategy=data.get("rotation_strategy", "round_robin"),
            enforce_secure_ip=data.get("enforce_secure_ip", True),
            max_retries=int(data.get("max_retries", 3)),
            cooldown_seconds=int(data.get("cooldown_seconds", 300)),
        )

    def to_dict(self) -> dict:
        """Returns the configuration as a dictionary."""
        return {
            "validation_url": self.validation_url,
            "timeout_seconds": self.timeout_seconds,
            "max_concurrent_checks": self.max_concurrent_checks,
            "rotation_strategy": self.rotation_strategy,
            "enforce_secure_ip": self.enforce_secure_ip,
            "max_retries": self.max_retries,
            "cooldown_seconds": self.cooldown_seconds,
        }

    def __str__(self) -> str:
        """Pretty string representation of the config."""
        return (
            f"ProxieConfig(\n"
            f"  Validation Target: {self.validation_url}\n"
            f"  Timeout: {self.timeout_seconds}s\n"
            f"  Concurrent Checks: {self.max_concurrent_checks}\n"
            f"  Rotation: {self.rotation_strategy}\n"
            f"  Kill-Switch: {'ENABLED' if self.enforce_secure_ip else 'DISABLED'}\n"
            f"  Max Retries: {self.max_retries}\n"
            f"  Cooldown: {self.cooldown_seconds}s\n"
            f")"
        )
