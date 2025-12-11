# 🕷️ Web Scraper Toolkit & MCP Server

![PyPI - Version](https://img.shields.io/pypi/v/web-scraper-toolkit?style=flat-square)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/web-scraper-toolkit?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)

**Version**: 0.1.2  
**Status**: Production Ready  
**Expertly Crafted by**: [Roy Dawson IV](https://github.com/imyourboyroy)

> A production-grade, multimodal scraping engine designed for **AI Agents**. Converts the web into LLM-ready assets (Markdown, JSON, PDF) with robust anti-bot evasion.

---

## 🚀 The "Why": AI-First Scraping

In the era of Agentic AI, tools need to be more than just Python scripts. They need to be **Token-Efficient**, **Self-Rectifying**, and **Structured**.

### ✨ Core Design Goals
*   **🤖 Hyper Model-Friendly**: All tools return standardized **JSON Envelopes**, separating metadata from content to prevent "context pollution."
*   **�️ Robust Failover**: Smart detection of anti-bot challenges (Cloudflare/403s) automatically triggers a switch from Headless to Visible browser mode to pass checks.
*   **🎯 Precision Control**: Use CSS Selectors (`selector`) and token limits (`max_length`) to extract *exactly* what you need, saving tokens and money.
*   **� Batch Efficiency**: The explicit `batch_scrape` tool handles parallel processing found in high-performance agent workflows.
*   **⚡ MCP Native**: Exposes a full Model Context Protocol (MCP) server for instant integration with Claude Desktop, Cursor, and other agentic IDEs.
*   **🔒 Privacy & Stealth**: Uses `playwright-stealth` and randomized user agents to mimic human behavior.

---

## 📦 Installation

### Option A: PyPI (Recommended)
Install directly into your environment or agent container.

```bash
pip install web-scraper-toolkit
playwright install
```

### Option B: From Source (Developers)
```bash
git clone https://github.com/imyourboyroy/WebScraperToolkit.git
cd WebScraperToolkit
pip install -e .
playwright install
```

---

## 🔌 MCP Server Integration

This is the primary way to use the toolkit with AI models. The server runs locally and exposes tools via the [Model Context Protocol](https://github.com/modelcontextprotocol).

### Running the Server
Once installed, simply run:
```bash
web-scraper-server --verbose
```

### Connecting to Claude Desktop / Cursor
Add the following to your agent configuration:

```json
{
  "mcpServers": {
    "web-scraper": {
      "command": "web-scraper-server",
      "args": ["--verbose"],
      "env": {
        "SCRAPER_WORKERS": "4"
      }
    }
  }
}
```

### 🧠 The "JSON Envelope" Standard
To ensure high reliability for Language Models, all tools return data in this strict JSON format:

```json
{
  "status": "success",  // or "error"
  "meta": {
    "url": "https://example.com",
    "timestamp": "2023-10-27T10:00:00",
    "format": "markdown"
  },
  "data": "# Markdown Content of the Website..."  // The actual payload
}
```
**Why?** This allows the model to instantly check `.status` and handle errors gracefully without hallucinating based on error text mixed with content.

### 🛠️ Available MCP Tools

| Tool | Description | Key Args |
| :--- | :--- | :--- |
| `scrape_url` | **The Workhorse.** Scrapes a single page. | `url`, `selector` (CSS), `max_length` |
| `batch_scrape` | **The Time Saver.** Parallel processing. | `urls` (List), `format` |
| `deep_research` | **The Agent.** Search + Crawl + Report. | `query` |
| `search_web` | Standard Search (DDG/Google). | `query` |
| `crawl_site` | Discovery tool for Sitemaps. | `url` |
| `save_pdf` | High-fidelity PDF renderer. | `url`, `path` |
| `configure_scraper` | Dynamic configuration. | `headless` (bool), `user_agent` |

---

## 💻 CLI Usage (Standalone)

For manual scraping or testing without the MCP server:

```bash
# Basic Markdown Extraction (Best for RAG)
web-scraper --url https://example.com --format markdown

# High-Fidelity PDF with Auto-Scroll
web-scraper --url https://example.com --format pdf

# Batch process a list of URLs from a file
web-scraper --input urls.txt --format json --workers 4

# Sitemap to JSON (Site Mapping)
web-scraper --input https://example.com/sitemap.xml --site-tree --format json
```

### 🛠️ CLI Reference

| Option | Shorthand | Description | Default |
| :--- | :--- | :--- | :--- |
| `--url` | `-u` | Single target URL to scrape. | `None` |
| `--input` | `-i` | Input file (`.txt`, `.csv`, `.json`, sitemap `.xml`) or URL. | `None` |
| `--format` | `-f` | Output: `markdown`, `pdf`, `screenshot`, `json`, `html`. | `markdown` |
| `--headless` | | Run browser in headless mode. (Off/Visible by default for stability). | `False` |
| `--workers` | `-w` | Number of concurrent workers. Pass `max` for CPU - 1. | `1` |
| `--merge` | `-m` | Merge all outputs into a single file. | `False` |
| `--site-tree` | | Extract URLs from sitemap input without crawling. | `False` |
| `--verbose` | `-v` | Enable verbose logging. | `False` |

---

## 🤖 Python API

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

## ⚙️ Server Configuration

You can configure the MCP server via Environment Variables:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `SCRAPER_WORKERS` | Number of concurrent browser processes. | `1` |
| `SCRAPER_VERBOSE` | Enable debug logs (`true`/`false`). | `false` |

---

## 📜 License
MIT License.

---
*Created with ❤️ by the Intelligence of Roy Dawson IV.*
