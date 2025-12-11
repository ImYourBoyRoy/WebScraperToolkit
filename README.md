# Web Scraper Toolkit & MCP Server

![PyPI - Version](https://img.shields.io/pypi/v/web-scraper-toolkit?style=flat-square)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/web-scraper-toolkit?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)

**Version**: 0.1.2  
**Status**: Production Ready  
**Expertly Crafted by**: [Roy Dawson IV](https://github.com/imyourboyroy)

---

## 🚀 The "Why": AI-First Scraping

**Web Scraper Toolkit** is a production-grade, autonomous scraping engine designed specifically for **AI Agents** and **LLMs**.

In the era of Agentic AI, tools need to be more than just Python scripts. They need to be **Token-Efficient**, **Self-Rectifying**, and **Structured**.

### Key Features
*   **🤖 Hyper Model-Friendly**: All tools return standardized **JSON Envelopes**, separating metadata from content to prevent "context pollution."
*   **📦 Batch Efficiency**: The explicit `batch_scrape` tool handles parallel processing found in high-performance agent workflows.
*   **🎯 Precision Control**: Use CSS Selectors (`selector`) and token limits (`max_length`) to extract *exactly* what you need, saving tokens and money.
*   **🛡️ Robust & stealthy**: Built on top of `Playwright-Stealth` with smart "Headless -> Headed" auto-recovery to bypass blocks (403/429).
*   **⚡ MCP Native**: Exposes a full Model Context Protocol (MCP) server for instant integration with Claude Desktop, Cursor, and other agentic IDEs.

---

## 📦 Installation

### Option A: PyPI (Recommended)
Install directly into your environment or agent container.

```bash
pip install web-scraper-toolkit
```

### Option B: From Source (Developers)
```bash
git clone https://github.com/imyourboyroy/WebScraperToolkit.git
cd WebScraperToolkit
pip install -e .
```

---

## 🔌 MCP Server Integration

This is the primary way to use the toolkit with AI models. The server runs locally and exposes tools via the [Model Context Protocol](https://github.com/modelcontextprotocol).

### Running the Server
Once installed, simply run:
```bash
web-scraper-server --verbose
```
*   `--verbose`: Enables detailed logging.
*   `--workers <N>`: Set specific worker count (default: 1).

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

---

## 🛠️ Available Tools

The MCP Server exposes the following tools to the AI Agent:

### 1. `scrape_url(url, format="markdown", selector=None, max_length=20000)`
**The Workhorse.** Scrapes a single page with anti-bot protection.
*   `selector`: (Optional) CSS selector (e.g., `article`, `#main-content`) to scrape ONLY that element. **Highly recommended for token efficiency.**
*   `max_length`: (Optional) Hard limit on returned characters.

### 2. `batch_scrape(urls: List[str], format="markdown")`
**The Time Saver.** Accepts a list of URLs and processes them in parallel using the server's process pool.
*   Returns a map: `{ "https://a.com": "content...", "https://b.com": "content..." }`

### 3. `deep_research(query: str)`
**The Agent.** Performs an autonomous deep dive:
1.  Searches DuckDuckGo/Google.
2.  Parses SERP results.
3.  **Crawls** the top 3 high-authority results.
4.  Returns a consolidated research report.

### 4. `search_web(query: str)`
Standard search tool. Returns a list of search results with snippets.

### 5. `crawl_site(url: str)` (or `get_sitemap`)
Discovery tool. Parses `sitemap.xml` or crawls the home page to find all valid sub-pages. Essential for mapping a domain before scraping.

### 6. `save_pdf(url: str, path: str)`
High-fidelity PDF renderer. Captures the page exactly as it renders, including layout and images.

### 7. `configure_scraper(headless=True, user_agent=None)`
Dynamic configuration. Allows the agent to toggle "Headed" mode for debugging or change identity on the fly.

---

## 💻 CLI Usage (Standalone)

For manual scraping or testing:

```bash
# Scrape a single URL to Markdown
web-scraper --url https://example.com

# Scrape and save as PDF
web-scraper --url https://example.com --format pdf --workers 2

# Batch process a list of URLs from a file
web-scraper --input urls.txt --format json --workers 4
```

---

## ⚙️ Configuration

You can configure the server via Environment Variables:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `SCRAPER_WORKERS` | Number of concurrent browser processes. | `1` |
| `SCRAPER_VERBOSE` | Enable debug logs (`true`/`false`). | `false` |

---

## 📜 License
MIT License.

---
*Generated with ❤️ by the Intelligence of Roy Dawson IV's Agent Swarm.*
