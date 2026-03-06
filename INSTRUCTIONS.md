# Web Scraper Toolkit - Operations & Deployment Guide

This document is the full runbook for humans and AI models.
Use this file when you need complete operational detail beyond the quick-start README.

---

## 1) Mode Selection (choose first)

- **CLI mode** (`web-scraper`)  
  Best for local scripts, CI jobs, and direct terminal workflows.

- **MCP mode** (`web-scraper-server`)  
  Best for agentic systems that need callable tools over stdio or HTTP transports.

- **Python embedding**  
  Best when toolkit must run inside your own Python runtime/process lifecycle.

---

## 2) Install + Bootstrap

### 2.1 Install

```bash
pip install web-scraper-toolkit
playwright install
```

Optional desktop challenge tooling:

```bash
pip install web-scraper-toolkit[desktop]
playwright install
```

### 2.2 Bootstrap config files

```bash
cp config.example.json config.json
cp settings.example.cfg settings.local.cfg
cp host_profiles.example.json host_profiles.json
```

If files are absent, toolkit can still run on defaults.  
When host learning is enabled, host profile storage is auto-created on first write.

---

## 3) How Runtime Resolution Works

Configuration precedence is deterministic:
1. CLI / MCP explicit inputs
2. `WST_*` environment variables
3. `settings.local.cfg` / `settings.cfg`
4. `config.json`
5. code defaults

This precedence applies to browser behavior, concurrency, timeout profiles, and server settings.

Default browser policy is Chromium-first (`browser_type=chromium`) with marker-driven native fallback.

---

## 4) CLI Operations (complete practical entry)

### 4.1 Basic scrape

```bash
web-scraper --url https://example.com --format markdown --export
```

### 4.2 Batch scrape

```bash
web-scraper --input urls.txt --workers auto --format text --merge --output-name merged.txt
```

### 4.3 Sitemap tree extraction

```bash
web-scraper --input https://example.com/sitemap.xml --site-tree --format json --output-name sitemap_tree.json
```

### 4.4 Domain crawl

```bash
web-scraper --input https://example.com --crawl --workers auto --format markdown
```

### 4.5 Contact extraction

```bash
web-scraper --url https://example.com --contacts --format json --export
```

### 4.6 Browser fallback tuning

```bash
web-scraper \
  --url https://target-site.tld/page \
  --native-fallback-policy on_blocked \
  --native-browser-channels chrome,msedge,chromium
```

Read-only host-profile apply mode:

```bash
web-scraper --url https://target-site.tld/page --host-profiles-read-only on
```

### 4.7 Host profile admin

Read host profile:

```bash
web-scraper --host-profile-host example.com
```

Manual host routing set:

```bash
web-scraper \
  --host-profile-host example.com \
  --host-profile-json "{\"routing\":{\"native_fallback_policy\":\"on_blocked\",\"native_browser_channels\":[\"chrome\",\"msedge\"],\"allow_headed_retry\":true,\"serp_strategy\":\"none\",\"serp_retry_policy\":\"none\",\"serp_retry_backoff_seconds\":12.0}}"
```

### 4.8 Script diagnostics through CLI wrapper

Toolkit-stage diagnostics:

```bash
web-scraper --run-diagnostic toolkit_route --diagnostic-url https://target-site.tld/resource
```

Matrix diagnostics:

```bash
web-scraper \
  --run-diagnostic challenge_matrix \
  --diagnostic-url https://target-site.tld/resource \
  --diagnostic-runs-per-variant 2 \
  --diagnostic-browser chrome
```

Toolkit diagnostics with gated host-profile auto-commit:

```bash
web-scraper \
  --run-diagnostic toolkit_route \
  --diagnostic-url https://target-site.tld/resource \
  --diagnostic-auto-commit-host-profile \
  --diagnostic-host-profiles-file ./host_profiles.json
```

Read-only diagnostics (apply existing profiles only, never write):

```bash
web-scraper --run-diagnostic toolkit_route --diagnostic-url https://target-site.tld/resource --diagnostic-read-only
```

Bot-surface diagnostics:

```bash
web-scraper --run-diagnostic bot_check --diagnostic-use-default-sites --diagnostic-screenshots
```

Browser telemetry diagnostics:

```bash
web-scraper --run-diagnostic browser_info
```

---

## 5) Diagnostic Scripts (direct invocation)

Use these when you need raw script behavior directly:

> Canonical diagnostic script naming is `diag_*.py`.
> Legacy non-`diag_` script names remain available as compatibility aliases.

```bash
python scripts/diag_toolkit_route.py --url https://target-site.tld/resource
python scripts/diag_toolkit_route.py --url https://target-site.tld/resource --require-2xx
python scripts/diag_toolkit_route.py --url https://target-site.tld/resource --require-2xx --save-artifacts --artifacts-dir ./scripts/out/artifacts
python scripts/diag_challenge_matrix.py --url https://target-site.tld/resource --runs-per-variant 2
python scripts/diag_bot_check.py --test-url https://example.com --browsers chromium,pw_chrome,system_chrome
python scripts/diag_browser_info.py
```

Output roots:
- `scripts/out/`

Workspace hygiene helper:

```bash
python scripts/clean_workspace.py --dry-run
```

---

## 6) Host Learning Lifecycle (auto domain routing)

### 6.1 Default learning behavior
- `host_profiles_enabled=true`
- `host_profiles_read_only=false`
- `host_learning_enabled=true`
- `host_learning_apply_mode="safe_subset"`
- `host_learning_promotion_threshold=2`

### 6.1.1 Read-only behavior
- `host_profiles_read_only=true` keeps host-profile routing apply-enabled.
- Learning writes are disabled while read-only is enabled.

### 6.2 What is auto-learned
- `native_fallback_policy` (`off|on_blocked` only)
- `native_browser_channels`
- `allow_headed_retry`
- `serp_strategy`
- `serp_retry_policy`
- `serp_retry_backoff_seconds` (bounded)

### 6.3 Promotion and demotion
- Promotion requires clean incognito successes (threshold default `2`).
- Persistent/session-backed runs are tracked but do not count for promotion.
- Repeated clean incognito failures can demote active routing.

### 6.4 Domain matching scope
- Host routing resolution order:
  1. explicit request overrides
  2. exact host profile (e.g., `api.example.com`)
  3. registrable domain profile (e.g., `example.com`)
  4. global browser config defaults
- Learning writes default to the registrable domain key unless an exact-host profile already exists.

---

## 7) MCP Server Operations

### 7.1 Local stdio (for desktop agents)

```bash
web-scraper-server --stdio
```

### 7.2 Remote transport

```bash
web-scraper-server --transport streamable-http --host 127.0.0.1 --port 8000 --path /mcp
```

### 7.3 API key protection

```bash
# Windows
set WST_MCP_API_KEY=your-secret

# Linux/macOS
export WST_MCP_API_KEY=your-secret

web-scraper-server --transport streamable-http --host 127.0.0.1 --port 8000 --path /mcp
```

### 7.4 MCP tool groups

- Scraping/discovery/content tools
- Browser interactive tools (`browser_*`), including:
  - explicit waits (`browser_wait_for`)
  - keyboard actions (`browser_press_key`)
  - scrolling/hover (`browser_scroll`, `browser_hover`)
  - compact element maps (`browser_get_interaction_map`)
  - accessibility snapshots (`browser_accessibility_tree`)
- Diagnostics tools:
  - `run_challenge_diagnostic(mode=toolkit|matrix, ...)`
    - supports `auto_commit_host_profile`, `host_profiles_path`, `read_only`
  - `run_bot_surface_diagnostic(...)`
  - `run_browser_info_diagnostic_tool(...)`
- Runtime/management tools
- Host profile management tools
- Async job orchestration (`start_job`, `poll_job`, etc.)

---

## 8) Security + Safety Controls

### 8.1 Recommended remote posture
1. Bind server to localhost/private network.
2. Put TLS reverse proxy in front.
3. Require API key for remote transport.
4. Keep context mode incognito by default.
5. Keep host learning on safe-subset mode.

### 8.2 OS-level input takeover safety
When challenge solving requires real mouse input:
- toolkit warns before takeover
- toolkit verifies browser/tab focus
- toolkit verifies active foreground window bounds
- toolkit refuses OS interaction in headless mode

Optional warning delay control:
- `WST_OS_INPUT_WARNING_SECONDS` (default `3`)

---

## 9) Ubuntu Service Deployment

### 9.1 Install runtime

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip

mkdir -p /opt/webscraper
cd /opt/webscraper
python3 -m venv .venv
source .venv/bin/activate
pip install web-scraper-toolkit
playwright install
```

### 9.2 Install systemd service (helper script)

```bash
sudo SERVICE_NAME=web-scraper-mcp \
  SERVICE_USER=ubuntu \
  INSTALL_DIR=/opt/webscraper \
  PYTHON_BIN=/opt/webscraper/.venv/bin/python \
  WST_SERVER_TRANSPORT=streamable-http \
  WST_SERVER_HOST=127.0.0.1 \
  WST_SERVER_PORT=8000 \
  WST_SERVER_PATH=/mcp \
  WST_MCP_API_KEY="$WST_MCP_API_KEY" \
  ./scripts/setup_mcp_service_ubuntu.sh
```

### 9.3 Service control

```bash
sudo systemctl start web-scraper-mcp
sudo systemctl stop web-scraper-mcp
sudo systemctl restart web-scraper-mcp
sudo systemctl status web-scraper-mcp
sudo journalctl -u web-scraper-mcp -f
```

Remove service:

```bash
sudo SERVICE_NAME=web-scraper-mcp ./scripts/remove_mcp_service_ubuntu.sh
```

---

## 10) Health Checks and Troubleshooting

### 10.1 Health checks

```bash
python scripts/healthcheck_mcp.py --url http://127.0.0.1:8000/mcp --api-key "$WST_MCP_API_KEY"
python verify_remote_mcp.py --remote-url https://your-domain/mcp --api-key "$WST_MCP_API_KEY"
```

### 10.2 Common failure patterns

- **Playwright browser missing**  
  Run `playwright install`.

- **Desktop solver unavailable**  
  Install desktop extra: `pip install web-scraper-toolkit[desktop]` and ensure GUI display is available.

- **Host profile store write error**  
  Check `host_profiles_path` permission/path and filesystem write access.

- **Remote MCP unauthorized**  
  Verify `WST_MCP_API_KEY` and proxy/header forwarding.

- **No output generated**  
  Verify `--output-dir`, format selection, and run permissions.

---

## 11) High-Value Environment Variables

- `WST_CONFIG_JSON`
- `WST_LOCAL_CFG`
- `WST_MCP_API_KEY`
- `WST_TIMEOUT_PROFILE`
- `WST_CLI_WORKERS_DEFAULT`
- `WST_MCP_PROCESS_WORKERS`
- `WST_MCP_INFLIGHT_LIMIT`
- `WST_MCP_BATCH_WORKERS`
- `WST_CRAWLER_DEFAULT_WORKERS`
- `WST_CRAWLER_MAX_WORKERS`
- `WST_SAFE_OUTPUT_ROOT`
- `WST_SERVER_TRANSPORT`
- `WST_SERVER_HOST`
- `WST_SERVER_PORT`
- `WST_SERVER_PATH`
- `WST_SERVER_REQUIRE_API_KEY`
- `WST_OS_INPUT_WARNING_SECONDS`

---

## 12) Author

Created by: **Roy Dawson IV**  
GitHub: <https://github.com/imyourboyroy>  
PyPi: <https://pypi.org/user/ImYourBoyRoy/>
