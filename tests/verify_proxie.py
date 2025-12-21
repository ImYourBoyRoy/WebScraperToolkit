# tests/verify_proxie.py
"""
Real-World Verification for Proxie Tool.
Loads 'config.json' and 'socks5_proxies.json' to test actual connectivity.
"""

import asyncio
import logging
import json
import os
import sys
import shutil

# Add src to path to ensure imports work
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from web_scraper_toolkit.proxie import ProxyManager, ProxieConfig, Proxy, ProxyProtocol
from web_scraper_toolkit.scraper import ProxyScraper


# Clear __pycache__
def clear_pycache():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pycache_path = os.path.join(
        root_dir, "src", "web_scraper_toolkit", "proxie", "__pycache__"
    )
    if os.path.exists(pycache_path):
        try:
            shutil.rmtree(pycache_path)
            print(f"🧹 Cleared {pycache_path}")
        except Exception as e:
            print(f"⚠️ Failed to clear pycache: {e}")


clear_pycache()

# Configure Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("RealWorldVerify")


def load_real_proxies():
    """Loads and merges proxy_account_config.json and socks5_proxies.json"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "proxy_account_config.json")
    list_path = os.path.join(base_dir, "socks5_proxies.json")

    if not os.path.exists(config_path) or not os.path.exists(list_path):
        logger.error("Proxy configuration files not found in root directory.")
        logger.error(f"  Expected: {config_path}")
        logger.error(f"  Expected: {list_path}")
        return [], None

    with open(config_path, "r") as f:
        creds = json.load(f)

    with open(list_path, "r") as f:
        raw_list = json.load(f)

    proxies = []
    for item in raw_list:
        proxies.append(
            Proxy(
                hostname=item["hostname"],
                port=int(creds["Port"]),
                username=creds["Username"],
                password=creds["Password"],
                protocol=ProxyProtocol.SOCKS5,  # Assuming SOCKS5 based on file name and config
            )
        )

    logger.info(f"Loaded {len(proxies)} proxies from {list_path}")
    return proxies, creds


async def main():
    logger.info("--- Starting Real-World Verification ---")

    proxies, creds = load_real_proxies()
    if not proxies:
        logger.error("No proxies loaded. Aborting.")
        return

    # Create Config
    config = ProxieConfig(
        enforce_secure_ip=True,
        timeout_seconds=10,
        max_concurrent_checks=50,
        rotation_strategy="round_robin",
    )

    logger.info("\n--- Configuration ---")
    logger.info(str(config))
    logger.info("---------------------\n")

    manager = ProxyManager(config, proxies)

    # 1. Initialize (Check Real IP & Validate Checks)
    logger.info("Initializing Manager (Checking Real IP & Validating Pool)...")
    await manager.initialize()

    active_count = sum(1 for p in manager.proxies if p.status.name == "ACTIVE")
    logger.info(f"Active Proxies: {active_count}/{len(proxies)}")

    if active_count == 0:
        logger.error("❌ No active proxies found! Check credentials or network.")
        return

    # 2. Rotation Test
    logger.info("\n--- Testing Rotation & Scraping ---")
    scraper = ProxyScraper(manager)

    test_urls = [
        "https://httpbin.org/ip",
        "https://httpbin.org/ip",
        "https://httpbin.org/ip",
    ]
    used_ips = set()

    for i, url in enumerate(test_urls):
        logger.info(f"\nRequest {i + 1}: Fetching IP...")
        content = await scraper.secure_fetch(url)

        if content:
            try:
                data = json.loads(content)
                origin = data.get("origin", "Unknown")
                logger.info(f"✅ Success! IP: {origin}")
                used_ips.add(origin)
            except json.JSONDecodeError:
                logger.error(f"❌ Failed to decode JSON: {content}")
        else:
            logger.error("❌ Request Failed.")

    logger.info(f"\nUnique IPs used: {len(used_ips)}")
    if len(used_ips) > 1:
        logger.info("✅ Rotation Confirmed (Multiple IPs used).")
    elif len(proxies) > 1:
        logger.warning(
            f"⚠️ Rotation Warning: Only 1 IP used out of {active_count} active proxies (Round Robin might be stuck or IPs are same)."
        )
    else:
        logger.info("ℹ️ Only 1 proxy available, rotation not expected.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Unhandled Error: {e}")
