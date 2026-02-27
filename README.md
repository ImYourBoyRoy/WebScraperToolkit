# Web Scraper Toolkit (Agentic + MCP Ready)

`web-scraper-toolkit` is a modular scraping and crawling toolkit designed for:
- **Agentic runtimes** (MCP clients like Claude Desktop, Cursor, custom orchestrators)
- **Programmatic Python usage**
- **CLI workflows for scripts and batch pipelines**

It focuses on robust extraction, safe automation, dynamic concurrency, and configurable runtime behavior without hardcoded operational limits.

Operational deployment guide: **`INSTRUCTIONS.md`** (Ubuntu/Windows/macOS service and remote runbooks).

---

## Why this toolkit

- **Agent-first MCP envelopes** (status/meta/data JSON response shape)
- **Dynamic concurrency** (CLI + MCP + crawler workers scale by host capacity/config)
- **Adaptive timeout profiles** (`fast`, `standard`, `research`, `long`)
- **Async job lifecycle for long tasks** (`start_job`, `poll_job`, `cancel_job`, `list_jobs`)
- **Remote MCP hosting support** (`stdio`, `http`, `sse`, `streamable-http`)
- **Optional API-key middleware** for remote MCP endpoints
- **Path safety rails** for file-writing tools (screenshot/pdf/download)

---

## Installation

```bash
pip install web-scraper-toolkit
playwright install
```

From source:

```bash
git clone https://github.com/imyourboyroy/WebScraperToolkit.git
cd WebScraperToolkit
pip install -e .
playwright install
```

---

## Runtime config hierarchy (important)

Effective precedence:

1. **CLI arguments**
2. **Environment variables** (`WST_*`)
3. **Local cfg override** (`settings.local.cfg` or `settings.cfg`)
4. **`config.json`**
5. **Built-in defaults**

Use `settings.example.cfg` as your local override template.

---

## Standalone usage (CLI)

Entry point:

```bash
web-scraper --help
```

Core examples:

```bash
# Single URL
web-scraper --url https://example.com --format markdown --export

# Batch input with dynamic workers
web-scraper --input urls.txt --format text --workers auto --merge --output-name merged.txt

# Sitemap tree extraction only
web-scraper --input https://example.com/sitemap.xml --site-tree --format json --output-name sitemap_tree.json

# Use custom config files
web-scraper --config ./config.json --local-config ./settings.local.cfg --url https://example.com
```

Key CLI options:

- `--url`, `--input`, `--crawl`
- `--format` (`markdown`, `text`, `html`, `metadata`, `screenshot`, `pdf`, `json`, `xml`, `csv`)
- `--workers` (`auto|max|dynamic|<int>`)
- `--delay`
- `--export`, `--merge`, `--output-dir`, `--temp-dir`, `--output-name`, `--clean`
- `--contacts`
- `--playbook`
- `--config`, `--local-config`
- `--headless`, `--verbose`, `--diagnostics`

---

## MCP server usage (agentic integration)

Entry point:

```bash
web-scraper-server --help
```

### Local stdio (recommended for desktop agents)

```bash
web-scraper-server --stdio
```

### Remote HTTP/streamable-http

```bash
web-scraper-server \
  --transport streamable-http \
  --host 0.0.0.0 \
  --port 8000 \
  --path /mcp
```

With API key:

```bash
set WST_MCP_API_KEY=your-secret-key
web-scraper-server --transport streamable-http --host 0.0.0.0 --port 8000 --path /mcp
```

Or:

```bash
web-scraper-server --transport streamable-http --api-key your-secret-key
```

### Recommended remote deployment shape (best practice)

1. Run MCP server as a **system service** on Ubuntu.
2. Put Nginx/Caddy in front for **TLS** termination.
3. Keep `require_api_key=true` for remote access.
4. Tune concurrency in `settings.local.cfg`.
5. Use `start_job/poll_job` for large workloads.

Example `systemd` unit:

```ini
[Unit]
Description=Web Scraper Toolkit MCP Server
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/webscraper
Environment=WST_MCP_API_KEY=change-me
ExecStart=/usr/bin/web-scraper-server --transport streamable-http --host 127.0.0.1 --port 8000 --path /mcp --config /opt/webscraper/config.json --local-config /opt/webscraper/settings.local.cfg
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

---

## MCP tools

### Scraping
- `scrape_url(url, selector?, max_length?, format?, timeout_profile?)`
- `batch_scrape(urls, format?, timeout_profile?, workers?)`
- `screenshot(url, path, timeout_profile?)`
- `save_pdf(url, path, timeout_profile?)`
- `get_metadata(url, timeout_profile?)`

### Discovery
- `get_sitemap(url, keywords?, limit?, timeout_profile?)`
- `crawl_site(url, timeout_profile?)`
- `extract_contacts(url, timeout_profile?)`
- `batch_contacts(urls, timeout_profile?)`
- `extract_links(url, filter_external?, timeout_profile?)`
- `search_web(query, timeout_profile?)`
- `deep_research(query, timeout_profile?)`

### Forms / utility
- `fill_form(url, fields, submit_selector?, save_session?, session_name?, timeout_profile?)`
- `extract_tables(url, table_selector?, timeout_profile?)`
- `click_element(url, selector, timeout_profile?)`
- `health_check()`
- `validate_url(url, timeout_profile?)`
- `detect_content_type(url, timeout_profile?)`
- `download_file(url, path, timeout_profile?)`

### Content
- `chunk_text(text, max_chunk_size?, overlap?)`
- `get_token_count(text, model?)`
- `truncate_text(text, max_tokens?, model?)`

### Management + runtime
- `configure_scraper(headless?, browser_type?, timeout_ms?)`
- `configure_stealth(respect_robots?, stealth_mode?)`
- `configure_runtime(overrides_json)`  
- `reload_runtime_config(config_path?, local_config_path?)`
- `get_config()`
- `configure_retry(max_attempts?, initial_delay?, max_delay?)`
- `clear_cache()`, `get_cache_stats()`
- `clear_session(session_id?)`, `new_session()`, `list_sessions()`
- `get_history(limit?)`, `clear_history()`
- `run_playbook(playbook_json, proxies_json?, timeout_profile?)`

### Async job lifecycle (long-running tasks)
- `start_job(job_type, payload_json, timeout_profile?)`
- `poll_job(job_id, include_result?)`
- `cancel_job(job_id)`
- `list_jobs(limit?)`

Supported `start_job` types:
- `batch_scrape`
- `deep_research`
- `run_playbook`
- `batch_contacts`

---

## Concurrency and timeout model

### Concurrency

- CLI workers resolve dynamically from host capacity when using `auto`.
- MCP process workers and inflight limits are dynamic/configurable.
- Batch operations use dedicated, configurable worker limits.
- Crawler defaults can be tuned globally in runtime config.

### Timeout profiles

Built-in profiles:
- `fast`
- `standard`
- `research`
- `long`

Profiles include:
- `soft_seconds`
- `hard_seconds`
- `extension_seconds`
- `allow_extension`

Timeouts are **scaled by work units** for batch/heavier calls.

---

## Fast result handling pattern (remote horsepower, local control)

For high parallel workloads (e.g., 40–80+ concurrent tasks on server hardware):

1. Call `start_job(...)` from your local agent/runtime.
2. Poll with `poll_job(job_id)` until terminal state.
3. Pull structured result payload into local memory/store.

This avoids long blocking calls and keeps laptop resources light.

---

## Remote file output strategy

If your goal is “compute remotely, consume locally,” prefer:

- `scrape_url`, `batch_scrape`, `extract_contacts`, `deep_research`
- async jobs (`start_job`/`poll_job`)

Use remote file tools only when explicitly needed:

- `screenshot`, `save_pdf`, `download_file`

All file writes are constrained to `runtime.safe_output_root`.
Set `safe_output_root` to an isolated directory if remote files are required.

---

## Config files

### `config.json`

Use the `runtime` section for dynamic behavior:

```json
{
  "runtime": {
    "default_timeout_profile": "standard",
    "safe_output_root": "./output",
    "concurrency": {
      "cli_workers_default": "auto",
      "mcp_process_workers": 0,
      "mcp_inflight_limit": 0,
      "mcp_batch_workers": 0,
      "crawler_default_workers": 0
    },
    "server": {
      "transport": "stdio",
      "host": "127.0.0.1",
      "port": 8000,
      "path": "/mcp",
      "require_api_key": false,
      "api_key_env": "WST_MCP_API_KEY"
    }
  }
}
```

### `settings.local.cfg` / `settings.cfg`

Use for machine/local overrides.  
See: `settings.example.cfg`.

---

## Environment variables

Common runtime env vars:

- `WST_CONFIG_JSON`
- `WST_LOCAL_CFG`
- `WST_TIMEOUT_PROFILE`
- `WST_MCP_PROCESS_WORKERS`
- `WST_MCP_INFLIGHT_LIMIT`
- `WST_MCP_BATCH_WORKERS`
- `WST_CLI_WORKERS_DEFAULT`
- `WST_SERVER_TRANSPORT`
- `WST_SERVER_HOST`
- `WST_SERVER_PORT`
- `WST_SERVER_PATH`
- `WST_SERVER_REQUIRE_API_KEY`
- `WST_SERVER_API_KEY_ENV`
- `WST_MCP_API_KEY`
- `WST_SAFE_OUTPUT_ROOT`

---

## Agent integration snippets

### Claude Desktop / Cursor style (stdio)

```json
{
  "mcpServers": {
    "web-scraper": {
      "command": "web-scraper-server",
      "args": ["--stdio"]
    }
  }
}
```

### Remote MCP endpoint

Point your client to:

`http://<host>:<port>/<path>`

with `x-api-key` header (or Bearer token) if enabled.

Python client example:

```python
import asyncio
from fastmcp import Client

async def main():
    async with Client("https://mcp.example.com/mcp", auth="YOUR_API_KEY") as client:
        result = await client.call_tool("start_job", {
            "job_type": "batch_scrape",
            "payload_json": "{\"urls\": [\"https://readyforus.app\", \"https://claragurney.com\"], \"format\": \"markdown\"}",
            "timeout_profile": "research"
        })
        print(result.data)

asyncio.run(main())
```

---

## Remote integration testing

### Smoke script (recommended)

```bash
python verify_remote_mcp.py --remote-url https://mcp.example.com/mcp --targets https://readyforus.app https://claragurney.com
```

Environment-based variant:

```bash
export WST_REMOTE_MCP_URL=https://mcp.example.com/mcp
export WST_REMOTE_MCP_API_KEY=your-secret-key
python verify_remote_mcp.py
```

### Pytest remote suite (optional)

```bash
export WST_REMOTE_MCP_URL=https://mcp.example.com/mcp
export WST_REMOTE_MCP_API_KEY=your-secret-key
pytest -q tests/test_remote_mcp_integration.py
```

These tests are skipped unless `WST_REMOTE_MCP_URL` is set.

---

## Notes

- No local machine paths, private hostnames, or private IPs should be committed.
- Keep secrets in environment variables or local cfg files ignored by git.
- For heavy remote deployments, tune concurrency + timeout profiles together.

---

## Author

Created by **Roy Dawson IV**  
GitHub: https://github.com/imyourboyroy  
PyPI: https://pypi.org/user/ImYourBoyRoy/
