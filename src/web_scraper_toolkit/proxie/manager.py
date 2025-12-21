# ./src/web_scraper_toolkit/proxie/manager.py
"""
Proxy Manager.

Handles the lifecycle, rotation, and validation of proxies.
Includes a Kill-Switch to prevent IP leaks.
"""

import logging
import asyncio
import aiohttp
import json
import random
import time
from typing import List, Optional
from aiohttp_socks import (
    ProxyConnector,
    ProxyType,
    ProxyError,
    ProxyTimeoutError,
    ProxyConnectionError,
)

from .models import Proxy, ProxyStatus, ProxyProtocol
from .config import ProxieConfig

logger = logging.getLogger(__name__)


class SecurityStopIteration(Exception):
    """Raised when the Kill-Switch is triggered or no safe proxies are available."""

    pass


class ProxyManager:
    def __init__(self, config: ProxieConfig, proxies: Optional[List[Proxy]] = None):
        self.config = config
        self.proxies: List[Proxy] = proxies or []
        self._lock = asyncio.Lock()
        self._current_index = 0
        self._last_revival_time = 0

        self._real_ip: Optional[str] = None

    async def initialize(self):
        """
        Initializes the manager:
        1. Determines Real IP (if enforcement is on).
        2. Validates initial proxy pool.
        """
        if self.config.enforce_secure_ip:
            await self._determine_real_ip()

        if self.proxies:
            await self.validate_all()

    async def _determine_real_ip(self):
        """Fetches the machine's real IP address for the Kill-Switch."""
        logger.info("Security Check: Determining Real IP...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.config.validation_url, timeout=self.config.timeout_seconds
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._real_ip = data.get("origin", "").split(",")[0].strip()
                        logger.info(
                            f"Security Check: Real IP identified as {self._real_ip}. Kill-Switch ACTIVE."
                        )
                    else:
                        logger.warning(
                            f"Security Check: Failed to determine Real IP (Status {response.status}). Kill-Switch may be ineffective."
                        )
        except Exception as e:
            logger.error(f"Security Check: Error determining Real IP: {e}")
            raise SecurityStopIteration(
                "Could not determine Real IP. Aborting for safety."
            )

    async def validate_proxy(self, proxy: Proxy) -> bool:
        """
        Validates a single proxy.
        Checks connection and ensures IP is not the Real IP.
        """
        connector = ProxyConnector(
            proxy_type=ProxyType.SOCKS5
            if proxy.protocol == ProxyProtocol.SOCKS5
            else ProxyType.HTTP,
            host=proxy.hostname,
            port=proxy.port,
            username=proxy.username,
            password=proxy.password,
            rdns=True,
        )

        try:
            start_time = time.time()
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    self.config.validation_url, timeout=self.config.timeout_seconds
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        remote_ip = data.get("origin", "").split(",")[0].strip()

                        if self.config.enforce_secure_ip and remote_ip == self._real_ip:
                            proxy.status = ProxyStatus.LEAKING
                            proxy.health_score = 0.0
                            logger.critical(
                                f"KILL-SWITCH: Proxy {proxy.hostname} leaked Real IP! Banning."
                            )
                            return False

                        proxy.status = ProxyStatus.ACTIVE
                        latency = (time.time() - start_time) * 1000
                        # Simple health update: reduce score if slow (> 2000ms)
                        proxy.health_score = max(
                            0.0, 100.0 - (max(0, latency - 500) / 50)
                        )
                        logger.debug(
                            f"Proxy {proxy.hostname} Valid. IP: {remote_ip}. Latency: {latency:.0f}ms"
                        )
                        return True
                    else:
                        proxy.status = ProxyStatus.DEAD
                        proxy.health_score -= 10
                        return False

        except (ProxyError, ProxyConnectionError, ProxyTimeoutError) as e:
            proxy.status = ProxyStatus.DEAD
            proxy.health_score -= 20
            logger.debug(f"Proxy {proxy.hostname} Error: {e}")
            return False
        except Exception as e:
            proxy.status = ProxyStatus.DEAD
            logger.debug(f"Proxy {proxy.hostname} Unexpected Error: {e}")
            return False

    async def validate_all(self):
        """Validates all proxies concurrently."""
        logger.info(f"Validating {len(self.proxies)} proxies...")
        tasks = [self.validate_proxy(p) for p in self.proxies]
        # Chunk tasks to respect max_concurrent_checks
        for i in range(0, len(tasks), self.config.max_concurrent_checks):
            chunk = tasks[i : i + self.config.max_concurrent_checks]
            await asyncio.gather(*chunk)

        active_count = sum(1 for p in self.proxies if p.status == ProxyStatus.ACTIVE)
        logger.info(
            f"Validation Complete. {active_count}/{len(self.proxies)} Proxies Active."
        )

        if active_count == 0:
            if self.config.enforce_secure_ip and any(
                p.status == ProxyStatus.LEAKING for p in self.proxies
            ):
                raise SecurityStopIteration(
                    "ALL proxies are either Dead or Leaking. Halting."
                )
            # If just dead, we might not raise SecurityStopIteration yet, but get_next will fail.

    def load_proxies_from_json(self, file_path: str):
        """Loads proxies from a JSON file."""
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
                # Handle list of dicts or {"proxies": [...]}
                proxy_list = (
                    data.get("proxies", data) if isinstance(data, dict) else data
                )

                new_proxies = []
                for p_data in proxy_list:
                    new_proxies.append(
                        Proxy(
                            hostname=p_data["hostname"],
                            port=int(p_data["port"]),
                            username=p_data.get("username"),
                            password=p_data.get("password"),
                            protocol=ProxyProtocol(p_data.get("protocol", "socks5")),
                        )
                    )
                self.proxies.extend(new_proxies)
                logger.info(f"Loaded {len(new_proxies)} proxies from {file_path}")
        except Exception as e:
            logger.error(f"Failed to load proxies from {file_path}: {e}")

    async def get_next_proxy(self) -> Proxy:
        """
        Gets the next active proxy based on rotation strategy.
        Thread-safe (async lock).
        """
        async with self._lock:
            active_proxies = [p for p in self.proxies if p.status == ProxyStatus.ACTIVE]

            if not active_proxies:
                # Hail Mary: Try to revive dead proxies if we haven't tried recently (e.g. last 60s)
                # or just try once per exhaustion event.
                if time.time() - self._last_revival_time > 60:
                    logger.warning(
                        "No active proxies! Attempting to revive DEAD proxies..."
                    )
                    await self._attempt_revival()
                    active_proxies = [
                        p for p in self.proxies if p.status == ProxyStatus.ACTIVE
                    ]
                    self._last_revival_time = time.time()

                if not active_proxies:
                    raise SecurityStopIteration(
                        "No active proxies available (Revival failed)."
                    )

            if self.config.rotation_strategy == "random":
                return random.choice(active_proxies)
            elif self.config.rotation_strategy == "health_weighted":
                # Basic weighted random
                total_health = sum(p.health_score for p in active_proxies)
                if total_health == 0:
                    return random.choice(active_proxies)
                pick = random.uniform(0, total_health)
                current = 0
                for p in active_proxies:
                    current += p.health_score
                    if current >= pick:
                        return p
                return active_proxies[-1]
            else:  # Round Robin
                # Find current index in active list
                proxy = active_proxies[self._current_index % len(active_proxies)]
                self._current_index += 1
                return proxy

    def report_status(
        self, proxy: Proxy, success: bool, status_code: Optional[int] = None
    ):
        """Updates proxy health based on request outcome."""
        proxy.total_calls += 1
        proxy.last_used_ts = time.time()

        if success:
            proxy.health_score = min(100.0, proxy.health_score + 1)
        else:
            proxy.failed_calls += 1
            if status_code == 403 or status_code == 429:
                proxy.status = ProxyStatus.COOLDOWN
                logger.warning(
                    f"Proxy {proxy.hostname} cooling down (Status {status_code})"
                )
                # Scheduled task to re-activate could go here,
                # for now rely on re-validation or manual reset if needed.
                # Ideally we spawn a background timer to reset it.
                asyncio.create_task(self._cooldown_timer(proxy))
            else:
                proxy.health_score -= 5
                if proxy.health_score < 30:
                    proxy.status = ProxyStatus.DEAD

    async def _cooldown_timer(self, proxy: Proxy):
        await asyncio.sleep(self.config.cooldown_seconds)
        async with self._lock:
            proxy.status = ProxyStatus.ACTIVE
            proxy.health_score = 50.0  # Reset to mid health
            logger.info(f"Proxy {proxy.hostname} returned from cooldown.")

    async def _attempt_revival(self):
        """Resets DEAD proxies to UNTESTED and triggers validation."""
        dead_proxies = [p for p in self.proxies if p.status == ProxyStatus.DEAD]
        if not dead_proxies:
            return

        for p in dead_proxies:
            p.status = ProxyStatus.UNTESTED

        logger.info(f"Reviving {len(dead_proxies)} dead proxies for re-validation.")
        await self.validate_all()
