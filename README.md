# 🕷️ Web Scraper Toolkit & MCP Server

![PyPI - Version](https://img.shields.io/pypi/v/web-scraper-toolkit?style=flat-square)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/web-scraper-toolkit?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)

**Expertly Crafted by**: [Roy Dawson IV](https://github.com/imyourboyroy)

> A production-grade, multimodal scraping engine designed for **AI Agents**. Converts the web into LLM-ready assets (Markdown, JSON, PDF) with robust anti-bot evasion.

---

## 🚀 The "Why": AI-First Scraping

In the era of Agentic AI, tools need to be more than just Python scripts. They need to be **Token-Efficient**, **Self-Rectifying**, and **Structured**.

### ✨ Core Design Goals
*   **🤖 Hyper Model-Friendly**: All tools return standardized **JSON Envelopes**, separating metadata from content to prevent "context pollution."
*   **🔍 Intelligent Sitemap Discovery**: **summary-first** approach prevents context flooding. Detects indices, provides counts, and offers **keyword deep-search** to find specific pages (e.g. "about", "contact") without reading the whole site.
*   **🛡️ Robust Failover**: Smart detection of anti-bot challenges (Cloudflare/403s) automatically triggers a switch from Headless to Visible browser mode to pass checks.
*   **🎯 Precision Control**: Use CSS Selectors (`selector`) and token limits (`max_length`) to extract *exactly* what you need, saving tokens and money.
*   **🔄 Batch Efficiency**: The explicit `batch_scrape` tool handles parallel processing found in high-performance agent workflows.
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

## 🏗️ Architecture & Best Practices

We support two distinct integration patterns depending on your needs:

### Pattern 1: The "Agentic" Way (MCP Server)
**Best for**: Claude Desktop, Cursor, Custom Agent Swarms.
*   **Mechanism**: Runs as a standalone process (stdio transport).
*   **Benefit**: **True Sandbox**. If the browser crashes, your Agent survives.
*   **Usage**: Use `web-scraper-server`.

### Pattern 2: The "Pythonic" Way (Library)
**Best for**: data pipelines, cron jobs, tight integration.
*   **Mechanism**: Direct import of `WebCrawler`.
*   **Benefit**: Simplicity. No subprocess management.
*   **Safety**: Internal scraping logic *still* uses `ProcessPoolExecutor` for isolation!

### 🏗️ Package Architecture

The codebase follows the **Single Responsibility Principle** with clean modular organization:

```
web_scraper_toolkit/
├── core/                    # Core utilities
│   ├── state/               # Cache, session, history management
│   ├── content/             # Text chunking, token counting
│   └── automation/          # Form filling, retry logic, utilities
├── parsers/                 # Content parsing
│   ├── extraction/          # Contact, metadata, media extraction
│   ├── search/              # Web search, SERP parsing
│   └── sitemap/             # Sitemap discovery and parsing
├── browser/                 # Playwright browser management
├── crawler/                 # Autonomous crawler engine (Proxie)
├── server/                  # MCP server
│   ├── handlers/            # Request handlers
│   └── mcp_tools/           # MCP tool implementations
├── playbook/                # Scraping playbook models
├── proxie/                  # Proxy management
└── scraper/                 # Low-level fetching engines
```

**Key Design Features:**
- **`core/`**: Centralized utilities with sub-packages for state, content, and automation
- **`parsers/`**: Content parsing with sub-packages for extraction and search
- **`server/mcp_tools/`**: Dedicated modules for Scraping, Search, Extraction, and Playbooks
- **Backward Compatible**: All exports available from main package imports

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

### 🛠️ Available MCP Tools (34 Total)

| Tool | Description | Key Args |
| :--- | :--- | :--- |
| **Scraping** | | |
| `scrape_url` | **The Workhorse.** Scrapes a single page. | `url`, `selector` (CSS), `max_length` |
| `batch_scrape` | **The Time Saver.** Parallel processing. | `urls` (List), `format` |
| `get_metadata` | Extract JSON-LD, OpenGraph, TwitterCards. | `url` |
| `screenshot` | Capture visual state. | `url`, `path` |
| `save_pdf` | High-fidelity PDF renderer. | `url`, `path` |
| **Discovery** | | |
| `get_sitemap` | **Smart Discovery**. Auto-filters noise. | `url`, `keywords` (e.g. "team"), `limit` |
| `crawl_site` | Alias for sitemap discovery. | `url` |
| `extract_contacts` | Autonomous Contact Extraction (JSON). | `url` |
| `batch_contacts` | Parallel contact extraction (hardware-limited). | `urls` (List) |
| `extract_links` | **NEW:** Extract all hyperlinks from page. | `url`, `filter_external` |
| **Search & Research** | | |
| `search_web` | Standard Search (DDG/Google). | `query` |
| `deep_research` | **The Agent.** Search + Crawl + Report. | `query` |
| **Form Automation** | | |
| `fill_form` | **Login/Form automation.** Session persistence. | `url`, `fields` (JSON), `submit_selector` |
| `extract_tables` | Get structured table data. | `url`, `table_selector` |
| `click_element` | Click elements (JS triggers). | `url`, `selector` |
| **File Operations** | | |
| `download_file` | Download PDFs, images, files. | `url`, `path` |
| **Autonomous** | | |
| `run_playbook` | **Autonomous Mode.** Execute complex JSON playbooks. | `playbook_json`, `proxies_json` |
| **Health & Validation** | | |
| `health_check` | System status check. | *(none)* |
| `validate_url` | Pre-flight URL check. | `url` |
| `detect_content_type` | Detect HTML/PDF/image. | `url` |
| **Configuration** | | |
| `configure_scraper` | Browser settings (headless mode). | `headless` (bool) |
| `configure_stealth` | **Robots.txt opt-out**, stealth mode. | `respect_robots`, `stealth_mode` |
| `configure_retry` | Exponential backoff settings. | `max_attempts`, `initial_delay` |
| `get_config` | View current configuration. | *(none)* |
| **Cache Management** | | |
| `clear_cache` | Clear response cache. | *(none)* |
| `get_cache_stats` | View cache hits/misses/size. | *(none)* |
| **Session Management** | | |
| `clear_session` | Clear browser session (cookies). | `session_id` |
| `new_session` | Start fresh browser session. | *(none)* |
| `list_sessions` | List saved sessions. | *(none)* |
| **Content Processing** | | |
| `chunk_text` | Split text for LLM context. | `text`, `max_chunk_size`, `overlap` |
| `get_token_count` | Estimate token count. | `text`, `model` |
| `truncate_text` | Truncate to token limit. | `text`, `max_tokens` |
| **History** | | |
| `get_history` | Get scraping history. | `limit` |
| `clear_history` | Clear history. | *(none)* |

> **Note**: By default, the toolkit respects `robots.txt`. To bypass (for authorized testing), call:
> ```
> configure_stealth(respect_robots=false)
> ```

---

## 🔍 Intelligent Sitemap Discovery

Unlike standard tools that dump thousands of URLs, this toolkit is designed for **Agent Context Windows**. 

### 1. Summary First
Returns a structural summary of Sitemaps before extraction.

### 2. Context-Aware Filtering
Use `get_sitemap(url, keywords="contact")` to find specific pages without crawling the entire site. The system recursively checks nested sitemaps but filters out low-value content (products, archives) automatically.

---

## 📞 Autonomous Contact Extraction

Built-in logic to extract business intelligence from any page.

**Capabilities:**
- **Emails**: Decodes Cloudflare-protected emails automatically.
- **Phones**: Extracts and formats international phone numbers.
- **Socials**: Identifies social media profiles (LinkedIn, Twitter, etc.).

**MCP Usage:**
`extract_contacts(url="https://example.com/contact")`

**Example Output:**
```markdown
**Identity**
- Business Name: Busy People
- Author Name: Roy Dawson

**Emails**
- contact@example.com
```

---

## 🦾 Advanced Usage: Autonomous Crawler (Proxie & Playbooks)

For complex, multi-step missions, use the **Autonomous Crawler**. It combines **Playbooks** (Strategy) with **Proxie** (Resilience).

### 1. Define a Playbook
Create a strictly typed strategy using `Playbook` and `Rule` models.

```python
from web_scraper_toolkit.playbook import Playbook, Rule, PlaybookSettings

playbook = Playbook(
    name="Forum Scraper",
    base_urls=["https://forum.example.com"],
    rules=[
        # Follow pagination
        Rule(type="follow", regex=r"/page-\d+"),
        # Extract specific thread data
        Rule(type="extract", regex=r"/threads/.*", extract_fields=[
            {"name": "title", "selector": "h1.thread-title"},
            {"name": "author", "selector": ".username"}
        ])
    ],
    settings=PlaybookSettings(
        respect_robots=True,
        validation_enabled=True,
        ai_context="Extract user sentiment from forum posts."
    )
)
```

### 2. Configure Proxies & Resilience
Manage IP rotation and security with `ProxieConfig`.

```python
from web_scraper_toolkit.proxie import ProxieConfig, ProxyManager, Proxy

# Load settings (can use config.json)
config = ProxieConfig(
    enforce_secure_ip=True,  # Kill-Switch if Real IP leaks
    max_retries=5,
    rotation_strategy="health_weighted"
)

# Initialize Manager
manager = ProxyManager(config, proxies=[
    Proxy(host="1.2.3.4", port=8080, username="user", password="pass"),
    # ...
])
```

### 3. Launch Mission
```python
from web_scraper_toolkit.crawler import ProxieCrawler

crawler = ProxieCrawler(playbook, manager)
await crawler.run()
# Results saved to results_Forum_Scraper.jsonl
```

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
| `--contacts` | | Autonomously extract emails/phones to output. | `False` |
| `--site-tree` | | Extract URLs from sitemap input without crawling. | `False` |
| `--verbose` | `-v` | Enable verbose logging. | `False` |

---

## 🤖 Python API

Integrate the `WebCrawler` directly into your Python applications.

```python
import asyncio
from web_scraper_toolkit import WebCrawler, BrowserConfig

async def agent_task():
    # 1. Configure
    config = BrowserConfig(
        headless=True,
        timeout=30000
    )
    
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

---

## ⚙️ Global Configuration

The toolkit supports a centralized `config.json` at the project root for managing defaults across all tools.

**Example `config.json`:**
```json
{
  "browser": {
    "headless": true,
    "browser_type": "chromium",
    "viewport_width": 1280,
    "viewport_height": 800,
    "timeout": 30000
  },
  "parser": {
    "ignore_links": false,
    "ignore_images": false,
    "body_width": 0,
    "extract_opengraph": true,
    "extract_twitter_cards": true
  },
  "sitemap": {
    "max_concurrent": 4,
    "max_depth": 3,
    "request_timeout": 15
  },
  "http": {
    "connection_pool_limit": 100,
    "connection_per_host": 10,
    "dns_cache_ttl": 300,
    "total_timeout": 30,
    "connect_timeout": 10
  },
  "retry": {
    "max_attempts": 3,
    "initial_delay_seconds": 1.0,
    "max_delay_seconds": 30.0,
    "exponential_base": 2.0,
    "jitter": true
  },
  "proxie": {
    "validation_url": "https://httpbin.org/ip",
    "timeout_seconds": 10,
    "max_concurrent_checks": 50,
    "rotation_strategy": "round_robin",
    "enforce_secure_ip": true,
    "max_retries": 3,
    "cooldown_seconds": 300
  },
  "crawler": {
    "default_user_agent": "WebScraperToolkit/1.0 (Crawler)",
    "default_max_depth": 3,
    "default_max_pages": 100,
    "default_crawl_delay": 1.0,
    "global_ignore_robots": false,
    "request_timeout": 30
  },
  "playbook": {
    "respect_robots": true,
    "max_depth": 3,
    "max_pages": 100,
    "crawl_delay": 1.0,
    "ai_context": false,
    "validation_enabled": false,
    "reuse_rules": true
  },
  "cache": {
    "enabled": true,
    "ttl_seconds": 300,
    "directory": "./cache",
    "max_size_mb": 100
  },
  "session": {
    "persist": true,
    "directory": "./sessions",
    "reuse_browser": true
  },
  "chunking": {
    "enabled": false,
    "max_chunk_size": 8000,
    "overlap": 200
  },
  "temp_directory": "./temp",
  "server": {
    "name": "Web Scraper Toolkit",
    "port": 8000,
    "host": "localhost",
    "log_level": "INFO"
  }
}
```

This file allows external agents (like Cursor or Claude) to inspect and modify behavioral defaults without code changes.

### Server Environment Variables
Override specific server settings via ENV:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `SCRAPER_WORKERS` | Number of concurrent browser processes. | `1` |
| `SCRAPER_VERBOSE` | Enable debug logs (`true`/`false`). | `false` |

---

## ✅ Verification & Testing

This project includes a comprehensive verification suite to ensure strict configuration enforcement, proxy resilience, and data integrity.

**Run the suite:**
```bash
python tests/verify_suite.py
```

**Example Output (Verified):**
```text
+-----------------------------------------------------------------------------+
| Running Test 01: Proxy Resilience (Hail Mary)                               |
+-----------------------------------------------------------------------------+
✔ Proxy Revival Triggered and Succeeded
Verify ProxyManager attempts 'Hail Mary' retry when all proxies are dead. ... ok

+-----------------------------------------------------------------------------+
| Running Test 02: Crawler Integrity (Persistence & Optimization)             |
+-----------------------------------------------------------------------------+
✔ Persistence Verified (results_IntegrityTest.jsonl)
✔ Rule Reuse Optimization Verified
Verify Crawler Rule Reuse and Persistence. ... ok

+-----------------------------------------------------------------------------+
| Running Test 03: BrowserConfig Enforcement                                  |
+-----------------------------------------------------------------------------+
✔ BrowserConfig Enforced
Verify WebCrawler strictly enforces BrowserConfig. ... ok

----------------------------------------------------------------------
Ran 3 tests in 2.383s

OK
SUCCESS: All tests passed.
```

---

## 📜 License
MIT License.

---
*Created with ❤️ by the Intelligence of Roy Dawson IV.*
