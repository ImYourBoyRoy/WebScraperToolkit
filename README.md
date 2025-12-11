# 🕷️ WebScraperToolkit

[![PyPI Version](https://img.shields.io/pypi/v/web_scraper_toolkit.svg)](https://pypi.org/project/web_scraper_toolkit/)
[![Python Versions](https://img.shields.io/pypi/pyversions/web_scraper_toolkit.svg)](https://pypi.org/project/web_scraper_toolkit/)
[![CI Status](https://github.com/imyourboyroy/WebScraperToolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/imyourboyroy/WebScraperToolkit/actions/workflows/ci.yml)
[![License](https://img.shields.io/pypi/l/web_scraper_toolkit.svg)](https://opensource.org/licenses/MIT)

> A production-grade, multimodal scraping engine designed for AI Agents. Converts the web into LLM-ready assets (Markdown, JSON, PDF) with robust anti-bot evasion.

---

## ✨ Design Goals

* **LLM Native**
  Output is optimized for context windows. Clean Markdown, semantic JSON Metadata, and noise-free text extraction.

* **Robust Failover**
  Smart detection of anti-bot challenges (Cloudflare/403s) automatically triggers a switch from Headless to Visible browser mode to pass checks.

* **Privacy & Stealth**
  Uses `playwright-stealth` and randomized user agents to mimic human behavior. Does not leak automation headers.

* **Agent Friendly**
  Fully typed Python API that integrates defining tools for MCP Servers using `fastmcp`.

* **Operational Excellence**
  * **Process Isolation**: Uses `ProcessPoolExecutor` to sandbox scraping tasks, preventing browser crashes from killing the main agent process.
  * **Unified Logging**: Centralized logging ensures consistent observability across CLI and Server modes.

---

## ⭐ Features

* **Multimodal Extraction**:
  * **Markdown**: Clean, structured text preserving headers, lists, and tables.
  * **PDF**: High-fidelity captures with auto-scroll enforcement for lazy-loaded assets.
  * **Screenshot**: Full-page visual captures.
  * **Metadata**: Extracts JSON-LD, OpenGraph, and meta tags.
* **Anti-Bot Evasion**:
  * "Smart Fetch" logic retries blocked requests in headed mode.
  * Spatial solver for Cloudflare Turnstile widgets.
* **Discovery**:
  * Sitemap parsing (XML) to extract all navigable URLs.
  * Recursive crawling for same-domain links.
* **Performance**:
  * Parallel processing via `asyncio` and `ProcessPoolExecutor`.
  * Customizable concurrency and politeness delays.

---

## 🚀 Installation

### PyPI (Recommended)
```bash
pip install web_scraper_toolkit
playwright install  # Required to download browser binaries
```

### From Source
```bash
# Clone and install
git clone https://github.com/imyourboyroy/WebScraperToolkit.git
cd WebScraperToolkit
pip install -e .
playwright install
```

> Requires Python 3.10+.

---

## 🧪 Quick Start

### CLI (Global Command)

```bash
# Basic Markdown Extraction (Best for RAG)
web-scraper --url https://example.com --format markdown

# High-Fidelity PDF with Auto-Scroll
web-scraper --url https://example.com --format pdf --output-name example.pdf

# Sitemap to JSON (Site Mapping)
web-scraper --input https://example.com/sitemap.xml --site-tree --format json --output-name map.json
```

### Standalone (No Install)
If you prefer running without full installation:
```bash
python scraper_cli.py --url https://example.com --format markdown
```

---

## 🛠️ CLI Reference

```bash
web-scraper [OPTIONS]
```

| Option | Shorthand | Description | Default |
| :--- | :--- | :--- | :--- |
| `--url` | `-u` | Single target URL to scrape. | `None` |
| `--input` | `-i` | Input file (`.txt`, `.csv`, `.json`, sitemap `.xml`) or URL. | `None` |
| `--format` | `-f` | Output: `markdown`, `pdf`, `screenshot`, `json`, `html`, `csv`. | `markdown` |
| `--headless` | | Run browser in headless mode. (Off/Visible by default for stability). | `False` |
| `--workers` | `-w` | Number of concurrent workers. Pass `max` for CPU - 1. | `1` |
| `--merge` | `-m` | Merge all outputs into a single file (e.g., one book PDF). | `False` |
| `--site-tree` | | Extract URLs from sitemap input without crawling content. | `False` |
| `--verbose` | `-v` | Enable verbose logging. | `False` |

---

## 🤖 Python API (for Agents/MCP)

Integrate the `WebCrawler` directly into your Python applications.

```python
import asyncio
from web_scraper_toolkit import WebCrawler, ScraperConfig

async def agent_task():
    # 1. Configure
    config = ScraperConfig.load({
        "scraper_settings": {"headless": True}, 
        "workers": 2
    })
    
    # 2. Instantiate
    crawler = WebCrawler(config=config)
    
    # 3. Run
    results = await crawler.run(
        urls=["https://example.com"],
        output_format="markdown",
        output_dir="./memory"
    )
    print(results)

if __name__ == "__main__":
    asyncio.run(agent_task())
```

---

## 📦 Versioning & Release

* **Versioning**: Follows Semantic Versioning (`0.1.0`), derived from Git tags.
* **CI/CD**: Automated testing and PyPI publication via GitHub Actions.
* **Release**: Create a tag (e.g. `v0.1.0`) to trigger a PyPI release.

---

## ✅ Verified Outputs

*Data matches exactly what the test script produces.*

**Command:**
`web-scraper --url https://example.com --format markdown --headless --verbose`

**StdOut:**
```text
2025-12-10 11:15:00 - DEBUG - Verbose logging enabled.

========================================
 Active Configuration
========================================
ScraperConfig:
{'delay': 0.0,
 'scraper_settings': {'headless': True, ...},
 'workers': 1}
========================================

--- Starting Single Target Scrape: https://example.com ---
Format: MARKDOWN
[1/1] Processing: https://example.com

--- Content Start ---
=== SCRAPED FROM: https://example.com/ (MARKDOWN) ===

# Example Domain

This domain is for use in documentation examples...
[Learn more](https://iana.org/domains/example)
--- Content End ---

Done.
```

---

## 🧰 Development

```bash
# Setup check
python run_tests.py

# Run verification suite
python scripts/verify_real_world.py
```

---

## 📜 License

MIT. See [LICENSE](LICENSE).

---

## ⭐ Support

**Created by**: Roy Dawson IV  
**GitHub**: [https://github.com/imyourboyroy](https://github.com/imyourboyroy)  
**PyPi**: [https://pypi.org/user/ImYourBoyRoy/](https://pypi.org/user/ImYourBoyRoy/)

If this tool helps you, star the repo and share it. Issues and PRs welcome.
