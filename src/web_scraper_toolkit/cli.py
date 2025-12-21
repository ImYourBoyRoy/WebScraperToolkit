# ./src/web_scraper_toolkit/cli.py
"""
Web Scraper Toolkit CLI
=======================

Primary entry point for the Web Scraper Toolkit.
Orchestrates the scraping workflow including URL loading, crawling,
processing, and exporting data in various formats.

Usage:
    python -m web_scraper_toolkit.cli [options]
    OR (installed)
    web-scraper [options]

Key Inputs:
    - --url: Single target URL.
    - --input: File (TXT, CSV, JSON, XML) or Sitemap URL.
    - --format: Output format (markdown, json, pdf, etc.).
    - --workers: Concurrency level.

Key Outputs:
    - Scraped content in 'output/' directory.
    - Console logs (Rich UI).
    - Exit Code 0 on success, 1 on failure.

Operational Notes:
    - Verifies dependencies at startup.
    - Supports headersless/headed switching via 'smart_fetch'.
"""

import asyncio
import argparse
import sys
import os
from . import (
    load_urls_from_source,
    WebCrawler,
    print_diagnostics,
    BrowserConfig,
    setup_logger,
)
from .core.verify_deps import verify_dependencies

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import json

# New Imports for Autonomous Mode
from .proxie import ProxyManager, ProxieConfig
from .crawler import AutonomousCrawler
from .playbook import Playbook

# Initialize Rich Console for pretty printing
console = Console()


def load_global_config(path="config.json"):
    """Loads the global config.json if it exists."""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load config.json: {e}")
    return {}


# Dependency Check
if not verify_dependencies():
    # We proceed but warn, or exit?
    # Proceed with execution but warn the user.
    # While dependencies are missing, core functionality might still be available in limited capacity.
    console.print("[yellow]⚠️  Proceeding with potential instability...[/yellow]")
    # sys.exit(1) # Uncomment to enforce strict mode

# Configure Logging via Central Logger
logger = setup_logger(verbose=False)


def parse_arguments(args=None, defaults=None):
    defaults = defaults or {}

    parser = argparse.ArgumentParser(description="Web Scraper Toolkit CLI")

    # Mode selection
    parser.add_argument(
        "--diagnostics", action="store_true", help="Run diagnostic checks."
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging."
    )

    # Input options
    parser.add_argument("--url", "-u", type=str, help="Target URL to scrape.")
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        help="Input file (txt, csv, json, xml sitemap) OR a single generic URL to crawl.",
    )
    parser.add_argument(
        "--crawl",
        action="store_true",
        help="If input is a single URL, crawl it for links (same domain).",
    )
    parser.add_argument(
        "--export", "-e", action="store_true", help="Export individual files."
    )
    parser.add_argument(
        "--contacts",
        action="store_true",
        help="Autonomously extract emails, phones, and socials.",
    )
    parser.add_argument(
        "--playbook",
        type=str,
        help="Path to a Playbook JSON file (enables Autonomous Mode).",
    )

    # Output format
    parser.add_argument(
        "--format",
        "-f",
        type=str,
        default="markdown",
        choices=[
            "markdown",
            "text",
            "html",
            "metadata",
            "screenshot",
            "pdf",
            "json",
            "xml",
            "csv",
        ],
        help="Output format.",
    )

    parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="Force Direct Mode (ignore proxies.json even if present).",
    )

    # Configuration
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run browser in headless mode (default: False/Visible).",
    )

    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge all output content into a single file.",
    )

    # Crawler options
    parser.add_argument(
        "--workers",
        "-w",
        type=str,
        default="1",
        help="Number of concurrent workers (default: 1). pass 'max' to use CPU_COUNT-1.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Delay (seconds) between requests per worker (default: 0).",
    )

    # Set default for headless from config if not specified (we can't easily do store_true default change in argparse
    # without making it a store_true/store_false pair, so we'll handle override in main logic)

    # Workflow options
    parser.add_argument(
        "--output-dir",
        type=str,
        default=".",
        help="Directory to save final output files.",
    )
    parser.add_argument(
        "--temp-dir",
        type=str,
        default=None,
        help="Directory for intermediate files (cleaned if --clean is used).",
    )
    parser.add_argument(
        "--output-name", type=str, help="Filename for the final merged output."
    )
    parser.add_argument(
        "--clean", action="store_true", help="Delete intermediate files after merging."
    )

    # Sitemap Tree Tool
    parser.add_argument(
        "--site-tree",
        action="store_true",
        help="Extract URLs from sitemap input without crawling content. Saves as CSV/JSON/XML.",
    )

    return parser.parse_args(args)


async def main_async():
    # 0. Load Global Config
    global_config = load_global_config()

    args = parse_arguments(defaults=global_config)

    # --- SITEMAP TREE MODE ---
    if args.site_tree and args.input:
        from . import extract_sitemap_tree

        console.print(
            f"[bold cyan]Extracting Sitemap Tree from:[/bold cyan] {args.input}"
        )
        urls = await extract_sitemap_tree(args.input)

        if not urls:
            console.print("[bold red]No URLs found.[/bold red]")
            sys.exit(1)

        # Determine output format
        if args.output_name:
            out_path = args.output_name
        else:
            base = "sitemap_tree"
            if args.format == "json":
                out_path = f"{base}.json"
            elif args.format == "xml":
                out_path = f"{base}.xml"
            else:
                out_path = f"{base}.csv"

        # Save (Logic identical, just UI update)
        if out_path.endswith(".json"):
            import json

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(urls, f, indent=2)
        elif out_path.endswith(".xml"):
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(
                    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                )
                for u in urls:
                    f.write(f"  <url><loc>{u}</loc></url>\n")
                f.write("</urlset>")
        else:
            with open(out_path, "w", encoding="utf-8") as f:
                for u in urls:
                    f.write(f"{u}\n")

        console.print(
            Panel(
                f"[green]Sitemap Tree saved to:[/green] {out_path} ({len(urls)} URLs)",
                title="Success",
            )
        )
        return

        return

    # --- AUTONOMOUS PLAYBOOK MODE ---
    if args.playbook:
        try:
            console.print(
                Panel(
                    f"[bold cyan]Launching Autonomous Playbook:[/bold cyan] {args.playbook}",
                    title="System Startup",
                )
            )

            # 1. Load Playbook
            with open(args.playbook, "r", encoding="utf-8") as f:
                playbook_data = json.load(f)
            playbook = Playbook(**playbook_data)

            # 2. Configure Proxie (Optional)
            manager = None
            proxie_config = None

            # Merge config.json 'proxie' settings with defaults (always load config)
            proxie_cfg_dict = global_config.get("proxie", {})
            proxie_config = ProxieConfig.from_dict(proxie_cfg_dict)

            # Check for proxy file (unless disabled)
            proxy_file = os.environ.get("PROXY_FILE", "proxies.json")
            if os.path.exists(proxy_file) and not args.no_proxy:
                # Load Proxies
                with open(proxy_file, "r") as f:
                    # basic list of dicts or {"proxies": []}
                    data = json.load(f)
                    p_list = (
                        data.get("proxies", data) if isinstance(data, dict) else data
                    )
                    proxies = [p for p in p_list]

                manager = ProxyManager(proxie_config, proxies)
                console.print(
                    f"[green]Proxy System Active: Loaded {len(proxies)} proxies.[/green]"
                )
                # Ideally initialize manager here if needed: await manager.initialize()
            else:
                msg = "Running in Direct (No-Proxy) Mode."
                if args.no_proxy:
                    msg += " (Forced by --no-proxy)"
                elif not os.path.exists(proxy_file):
                    msg += " (No proxies.json found)"
                console.print(f"[dim]{msg}[/dim]")

            # 3. Launch Crawler
            # AutonomousCrawler handles Playwright + Optional Proxy internally
            crawler = AutonomousCrawler(playbook, proxy_manager=manager)
            await crawler.run()

            console.print(
                Panel(
                    f"[bold green]Playbook Completed![/bold green]\nResults saved to: {crawler.results_filename}",
                    title="Success",
                )
            )
            return

        except Exception as e:
            console.print(f"[bold red]Playbook Failed:[/bold red] {e}")
            logger.exception("Playbook execution failed")
            sys.exit(1)

    # --- STANDARD MODE (Legacy/Direct) ---

    # Determine worker count
    worker_count = 1
    if args.workers.lower() == "max":
        try:
            cpu_count = os.cpu_count() or 1
            worker_count = max(1, cpu_count - 1)
        except Exception:
            worker_count = 1
    else:
        try:
            worker_count = int(args.workers)
            if worker_count < 1:
                worker_count = 1
        except ValueError:
            logger.error(f"Invalid worker count: {args.workers}. Defaulting to 1.")
            worker_count = 1

    # Diagnostics check
    if args.diagnostics:
        print_diagnostics()
        return

    # 1. Gather URLs
    target_urls = []
    if args.url:
        target_urls.append(args.url)
    elif args.input:
        target_urls = await load_urls_from_source(args.input)
        console.print(f"[dim]Loaded {len(target_urls)} URLs from source[/dim]")

        if not target_urls and args.input.startswith("http"):
            if "sitemap" not in args.input and not args.input.endswith(".xml"):
                console.print(
                    "[yellow]⚠️  Input looked like a webpage URL but not a sitemap.[/yellow]"
                )
                console.print("   Use --url for single pages.")

    if not target_urls:
        console.print("[bold red]No URLs found to process.[/bold red]")
        sys.exit(1)

    # 2. Configuration Setup
    # Merge global config with CLI args

    # CLI args take precedence over config.json
    # Logic: If CLI arg is False (default) BUT config is True, valid?
    # Logic: Config.json defines the BASE configuration.
    # Argparse overrides if the flag is explicitly set (True).
    # Browser Mode Logic:
    # CLI --headless flag takes precedence. If not specified, config.json default is used.
    # For max reliability, smart_fetch() auto-switches to headed mode if anti-bot is detected.

    browser_defaults = global_config.get("browser", {})

    # If args.headless is explicitly True, use it. Else use config default.
    # (Simplified logic: OR logic might be safer for "headless" if default is visible)

    final_headless = args.headless or browser_defaults.get("headless", False)
    # Headless Mode: smart_fetch() handles automatic failover to headed mode when needed.

    b_config = BrowserConfig(
        headless=final_headless,
        browser_type=browser_defaults.get("browser_type", "chromium"),
        timeout=browser_defaults.get("timeout", 30000),
    )

    # Print Active Config (Only in Verbose Mode - Rich Style)
    if args.verbose:
        config_table = Table(
            title="Active Configuration", show_header=True, header_style="bold magenta"
        )
        config_table.add_column("Key", style="cyan")
        config_table.add_column("Value", style="green")

        config_table.add_row("Workers", str(worker_count))
        config_table.add_row("Delay", str(args.delay))
        config_table.add_row("Headless", str(b_config.headless))
        config_table.add_row("Output Dir", args.output_dir)

        console.print(config_table)

    # 3. Instantiate and Run Crawler
    crawler = WebCrawler(config=b_config, workers=worker_count, delay=args.delay)
    await crawler.run(
        urls=target_urls,
        output_format=args.format,
        export=args.export,
        merge=args.merge,
        output_dir=args.output_dir,
        temp_dir=args.temp_dir,
        clean=args.clean,
        output_filename=args.output_name,
        extract_contacts=args.contacts,
    )


def main():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
