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
    ScraperConfig,
    setup_logger,
)

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Initialize Rich Console for pretty printing
console = Console()

# Dependency Check
from .core.verify_deps import verify_dependencies

if not verify_dependencies():
    # We proceed but warn, or exit?
    # User said "gently fail", which usually means "don't crash with traceback".
    # Since verify_deps prints critical instructions, let's pause or exit gracefully.
    console.print("[yellow]⚠️  Proceeding with potential instability...[/yellow]")
    # sys.exit(1) # Uncomment to enforce strict mode

# Configure Logging via Central Logger
logger = setup_logger(verbose=False)


def parse_arguments(args=None):
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
        "--merge", "-m", action="store_true", help="Merge all outputs into one file."
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

    # Configuration
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run browser in headless mode (default: False/Visible).",
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
    args = parse_arguments()

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
    overrides = {
        "scraper_settings": {"headless": args.headless, "browser_type": "chromium"},
        "workers": worker_count,
        "delay": args.delay,
        "output_dir": args.output_dir,
        "temp_dir": args.temp_dir,
    }

    config = ScraperConfig.load(overrides)

    # Print Active Config (Only in Verbose Mode - Rich Style)
    if args.verbose:
        config_table = Table(
            title="Active Configuration", show_header=True, header_style="bold magenta"
        )
        config_table.add_column("Key", style="cyan")
        config_table.add_column("Value", style="green")

        config_table.add_row("Workers", str(config.workers))
        config_table.add_row("Delay", str(config.delay))
        config_table.add_row("Headless", str(config.scraper_settings.headless))
        config_table.add_row("Output Dir", overrides["output_dir"])

        console.print(config_table)

    # 3. Instantiate and Run Crawler
    crawler = WebCrawler(config=config, workers=config.workers, delay=config.delay)
    await crawler.run(
        urls=target_urls,
        output_format=args.format,
        export=args.export,
        merge=args.merge,
        output_dir=args.output_dir,
        temp_dir=args.temp_dir,
        clean=args.clean,
        output_filename=args.output_name,
    )


def main():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
