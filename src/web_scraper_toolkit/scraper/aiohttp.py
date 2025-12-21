# ./src/web_scraper_toolkit/scraper/aiohttp.py
"""
Proxy Scraper (aiohttp).

Handles reliable and secure data fetching using the Proxy Manager.
Ensures requests are routed through valid proxies and retries on failure.
"""

import logging
import asyncio
import aiohttp
from typing import Optional, Dict
from aiohttp_socks import (
    ProxyConnector,
    ProxyType,
    ProxyError,
    ProxyConnectionError,
    ProxyTimeoutError,
)

from ..proxie.manager import ProxyManager, SecurityStopIteration
from ..core.user_agents import get_stealth_headers

logger = logging.getLogger(__name__)


class ProxyScraper:
    def __init__(self, manager: Optional[ProxyManager] = None):
        self.manager = manager

    async def secure_fetch(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> Optional[str]:
        """
        Fetches a URL securely using the proxy pool.
        Automatically rotates proxies on failure.

        Args:
            url: Target URL.
            method: HTTP method (GET, POST).
            headers: HTTP headers (will be merged with stealth defaults).
            **kwargs: Additional args passed to aiohttp (e.g., json, data).

        Returns:
            Response text if successful, None if all retries failed.
        """
        # Determine Retries (Config or Default)
        retries = self.manager.config.max_retries if self.manager else 2

        for attempt in range(retries + 1):  # +1 to ensure at least one try
            proxy = None
            connector = None

            try:
                # 1. Get Proxy (if Manager exists)
                if self.manager:
                    proxy = await self.manager.get_next_proxy()

                    # Build Proxy Connector
                    connector = ProxyConnector(
                        proxy_type=ProxyType.SOCKS5
                        if proxy.protocol.value == "socks5"
                        else ProxyType.HTTP,
                        host=proxy.hostname,
                        port=proxy.port,
                        username=proxy.username,
                        password=proxy.password,
                        rdns=True,
                    )
                    log_prefix = f"Fetching {url} via {proxy.hostname}"
                else:
                    # Direct Mode
                    log_prefix = f"Fetching {url} (Direct)"

                # 2. Execute Request with Stealth Headers
                logger.debug(f"{log_prefix} (Attempt {attempt + 1})")

                # Timeout logic
                timeout = self.manager.config.timeout_seconds if self.manager else 10

                # Merge user headers with stealth defaults
                request_headers = get_stealth_headers(headers)

                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.request(
                        method,
                        url,
                        headers=request_headers,
                        timeout=timeout,
                        **kwargs,
                    ) as response:
                        content = await response.text()
                        status = response.status

                        # Success
                        if status == 200:
                            if self.manager and proxy:
                                self.manager.report_status(proxy, success=True)

                            # Basic check for "Javascript Required" bodies
                            if (
                                "enable javascript" in content.lower()
                                or "javascript is disabled" in content.lower()
                            ):
                                logger.warning(
                                    f"Static Fetch detected JS requirement on {url}"
                                )
                                return None  # Signal caller to try Playwright

                            logger.info(f"Success: {url} fetched.")
                            return content

                        # Handle Blocks/Errors
                        elif status in [403, 429]:
                            if self.manager and proxy:
                                self.manager.report_status(
                                    proxy, success=False, status_code=status
                                )
                                logger.warning(
                                    f"Blocked ({status}) on {url} via {proxy.hostname}. Rotating."
                                )
                            else:
                                logger.warning(f"Blocked ({status}) on {url} (Direct).")
                                return None  # Direct fail -> Try Playwright
                        else:
                            if self.manager and proxy:
                                self.manager.report_status(
                                    proxy, success=False, status_code=status
                                )
                            logger.warning(f"Failed ({status}) on {url}.")
                            if not self.manager:
                                return None  # Direct fail -> Stop or Fallback

            except SecurityStopIteration as e:
                logger.critical(f"Security Stop: {e}")
                raise
            except (ProxyError, ProxyConnectionError, ProxyTimeoutError) as e:
                if self.manager and proxy:
                    self.manager.report_status(proxy, success=False)
                logger.warning(f"Proxy Error: {e}")
            except Exception as e:
                if self.manager and proxy:
                    self.manager.report_status(proxy, success=False)
                logger.error(f"Error fetching {url}: {e}")

            # Wait before retry
            await asyncio.sleep(1)

        return None
