# ./src/web_scraper_toolkit/cli.py
"""
Web Scraper Toolkit CLI public facade preserving legacy module imports.
Run: `python -m web_scraper_toolkit.cli` or installed `web-scraper` entrypoint.
Inputs: CLI flags, config files, environment vars, and optional playbook/proxy files.
Outputs: crawler/diagnostic workflows, console reports, and generated output artifacts.
Side effects: reads/writes local files, starts browsers, and may exit with non-zero code.
Operational notes: heavy logic is split into private `_cli` modules to avoid monolith growth.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import (
    BrowserConfig,
    WebCrawler,
    load_urls_from_source,
    print_diagnostics,
    setup_logger,
)
from ._cli.arguments import _normalize_diagnostic_name, parse_arguments
from ._cli.bootstrap import bootstrap_default_config_files, load_global_config
from ._cli.runner import run_main_async
from .core.runtime import load_runtime_settings, resolve_worker_count
from .core.verify_deps import verify_dependencies
from .crawler import AutonomousCrawler
from .playbook import Playbook
from .proxie import ProxieConfig, ProxyManager

console = Console()

if not verify_dependencies():
    console.print("[yellow]⚠️  Proceeding with potential instability...[/yellow]")

logger = setup_logger(verbose=False)


async def main_async() -> None:
    from . import extract_sitemap_tree

    await run_main_async(
        parse_arguments_fn=parse_arguments,
        normalize_diagnostic_name_fn=_normalize_diagnostic_name,
        bootstrap_default_config_files_fn=bootstrap_default_config_files,
        load_global_config_fn=load_global_config,
        load_runtime_settings_fn=load_runtime_settings,
        resolve_worker_count_fn=resolve_worker_count,
        console=console,
        logger=logger,
        load_urls_from_source_fn=load_urls_from_source,
        WebCrawlerCls=WebCrawler,
        BrowserConfigCls=BrowserConfig,
        print_diagnostics_fn=print_diagnostics,
        ProxyManagerCls=ProxyManager,
        ProxieConfigCls=ProxieConfig,
        AutonomousCrawlerCls=AutonomousCrawler,
        PlaybookCls=Playbook,
        extract_sitemap_tree_fn=extract_sitemap_tree,
        PanelCls=Panel,
        TableCls=Table,
        os_module=os,
        sys_module=sys,
        json_module=json,
        asyncio_module=asyncio,
    )


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main_async())


__all__ = [
    "console",
    "logger",
    "parse_arguments",
    "_normalize_diagnostic_name",
    "load_global_config",
    "bootstrap_default_config_files",
    "main_async",
    "main",
    "WebCrawler",
    "load_urls_from_source",
]


if __name__ == "__main__":
    main()
