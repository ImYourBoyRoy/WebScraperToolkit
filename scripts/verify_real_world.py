
import asyncio
import os
import sys
import shutil
from datetime import datetime
from rich.console import Console
from rich.table import Table

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from web_scraper_toolkit.browser.playwright_handler import PlaywrightManager
from web_scraper_toolkit.parsers.html_to_markdown import MarkdownConverter
from web_scraper_toolkit.server import mcp_server

console = Console()
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../tests_output'))

async def run_verification():
    console.print("[bold blue]🚀 Starting Real-World Integration Verification[/bold blue]")
    
    # 0. Setup
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)
    console.print(f"[dim]Output Directory: {OUTPUT_DIR}[/dim]\n")

    results = []
    
    # --- TEST 1: Basic Scrape (Markdown) ---
    console.print("[yellow]Testing Markdown Scrape...[/yellow]")
    url = "https://example.com"
    config = {
        "scraper_settings": {
            "headless": True,
            "browser_type": "chromium"
        }
    }
    
    try:
        async with PlaywrightManager(config) as manager:
            content, final_url, status = await manager.smart_fetch(url)
            
            if status == 200 and content:
                md_path = os.path.join(OUTPUT_DIR, "example.md")
                markdown = MarkdownConverter.to_markdown(content, base_url=final_url)
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(markdown)
                
                size = os.path.getsize(md_path)
                results.append(["Markdown Extraction", "example.md", f"{size} bytes", "[green]PASS[/green]"])
            else:
                results.append(["Markdown Extraction", "example.md", "0", f"[red]FAIL (Status {status})[/red]"])
    except Exception as e:
        results.append(["Markdown Extraction", "N/A", "Error", f"[red]FAIL: {e}[/red]"])

    # --- TEST 2: Screenshot ---
    console.print("[yellow]Testing Screenshot...[/yellow]")
    img_path = os.path.join(OUTPUT_DIR, "example.png")
    try:
        async with PlaywrightManager(config) as manager:
            success, status = await manager.capture_screenshot(url, img_path)
            if success and os.path.exists(img_path):
                size = os.path.getsize(img_path)
                results.append(["Screenshot", "example.png", f"{size} bytes", "[green]PASS[/green]"])
            else:
                results.append(["Screenshot", "example.png", "0", "[red]FAIL[/red]"])
    except Exception as e:
        results.append(["Screenshot", "N/A", "Error", f"[red]FAIL: {e}[/red]"])

    # --- TEST 3: PDF Generation ---
    console.print("[yellow]Testing PDF Generation...[/yellow]")
    pdf_path = os.path.join(OUTPUT_DIR, "example.pdf")
    try:
        # PDF requires headless=True, which is set
        async with PlaywrightManager(config) as manager:
            success, status = await manager.save_pdf(url, pdf_path)
            if success and os.path.exists(pdf_path):
                size = os.path.getsize(pdf_path)
                results.append(["PDF Generation", "example.pdf", f"{size} bytes", "[green]PASS[/green]"])
            else:
                 results.append(["PDF Generation", "example.pdf", "0", "[red]FAIL[/red]"])
    except Exception as e:
        results.append(["PDF Generation", "N/A", "Error", f"[red]FAIL: {e}[/red]"])

    # --- TEST 4: MCP Server Link (Logic Check) ---
    # console.print("[yellow]Testing MCP Server Logic...[/yellow]")
    # Skipped to prevent ProcessPoolExecutor hangs in script mode
    results.append(["MCP Logic", "Skipped", "N/A", "[yellow]SKIPPED (Process Lock Safety)[/yellow]"])


    # --- REPORTING ---
    console.print("\n")
    table = Table(title="Integration Verification Results")
    table.add_column("Test Case", style="cyan")
    table.add_column("Output File/Target", style="magenta")
    table.add_column("Size/Info", style="white")
    table.add_column("Status", style="bold")

    for row in results:
        table.add_row(*row)

    console.print(table)
    console.print(f"\n[bold green]Verify artifacts in:[/bold green] {OUTPUT_DIR}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(run_verification())
