# ./src/web_scraper_toolkit/server/handlers/playbook.py
"""
Implement MCP-facing playbook execution handlers.
Used by management tools to run autonomous crawler playbooks from JSON payloads.
Run: Imported by MCP server modules; no standalone CLI entry point.
Inputs: Serialized playbook JSON and optional proxy list JSON.
Outputs: In-memory crawl results produced by `AutonomousCrawler`.
Side effects: Executes network crawling and may write crawler artifacts.
Operational notes: Proxy payloads are normalized into strongly-typed proxy models.
"""

from __future__ import annotations

import json
from ...crawler import AutonomousCrawler
from ...playbook.models import Playbook, Rule, PlaybookSettings
from ...proxie import ProxyManager, ProxieConfig, Proxy


async def execute_playbook(playbook_json: str, proxies_json: str | None = None) -> list:
    """Executes a playbook."""
    pb_data = json.loads(playbook_json)
    rules = [Rule(**r) for r in pb_data.get("rules", [])]
    settings = PlaybookSettings(**pb_data.get("settings", {}))

    playbook = Playbook(
        name=pb_data.get("name", "Agent Playbook"),
        base_urls=pb_data.get("base_urls", []),
        rules=rules,
        settings=settings,
    )

    proxies = []
    if proxies_json:
        p_list = json.loads(proxies_json)
        for p in p_list:
            proxies.append(Proxy(**p))

    config = ProxieConfig()
    manager = ProxyManager(config, proxies)

    crawler = AutonomousCrawler(playbook, proxy_manager=manager)
    await crawler.run()

    return crawler.results
