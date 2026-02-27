# Web Scraper Toolkit Remote/Service Instructions

This guide is the operational companion to `README.md`.

Use this for:
- Ubuntu/Linux remote service setup
- Windows local/remote host operation
- macOS host operation
- Health checks and safe start/stop workflows

---

## 1) Quick decision matrix

- **Local desktop MCP use (Claude/Cursor, etc.)**  
  Use `web-scraper-server --stdio` (or scripts for local background process).

- **Remote high-horsepower MCP host**  
  Use `streamable-http` transport + API key + TLS reverse proxy.

- **Massive parallel jobs**  
  Use async MCP jobs: `start_job` + `poll_job`.

---

## 2) Ubuntu (20.04 / 22.04 / 24.04)

All three are supported with the same flow.

### A. Install

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

Optional from source:

```bash
git clone https://github.com/imyourboyroy/WebScraperToolkit.git /opt/webscraper
cd /opt/webscraper
source .venv/bin/activate
pip install -e .
playwright install
```

### B. Configure

```bash
cp settings.example.cfg settings.local.cfg
```

Set key runtime values in `settings.local.cfg`:
- concurrency
- timeout profiles
- server transport/host/port/path
- `require_api_key=true` for remote use

Set API key:

```bash
export WST_MCP_API_KEY="change-me"
```

### C. Run as systemd service (recommended)

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

Manage service:

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

### D. Health check

```bash
python scripts/healthcheck_mcp.py --url http://127.0.0.1:8000/mcp --api-key "$WST_MCP_API_KEY"
```

Full remote smoke check:

```bash
python verify_remote_mcp.py --remote-url https://your-domain/mcp --api-key "$WST_MCP_API_KEY"
```

---

## 3) Linux/macOS start/stop scripts (non-systemd mode)

```bash
./scripts/start_server.sh
./scripts/status_server.sh
./scripts/stop_server.sh
```

These scripts:
- run MCP server in background
- store PID in `.runtime/web_scraper_mcp.pid`
- write logs in `.runtime/`
- run post-start health check automatically

---

## 4) Windows start/stop scripts

From repository root:

```bat
scripts\start_server.bat
scripts\status_server.bat
scripts\stop_server.bat
```

These call PowerShell scripts:
- `scripts/start_server.ps1`
- `scripts/status_server.ps1`
- `scripts/stop_server.ps1`

---

## 5) Remote connection model (best practice)

### A. Topology

1. MCP server on remote host (`127.0.0.1:8000/mcp` internally)
2. TLS reverse proxy exposes `https://your-domain/mcp`
3. Agent/client connects with API key

### B. Client endpoint

Point MCP client to:

`https://your-domain/mcp`

Include:
- `x-api-key: <key>` header  
  or  
- `Authorization: Bearer <key>`

---

## 6) High-throughput usage pattern (recommended)

For large parallel loads (40–80+):

1. Submit:
   - `start_job(job_type="batch_scrape", payload_json=...)`
2. Poll:
   - `poll_job(job_id)`
3. Consume result locally:
   - parse returned JSON envelope data

This keeps heavy computation remote while your local machine only orchestrates and consumes results.

---

## 7) Remote file output strategy

Recommended default:
- avoid remote file output unless required
- keep workflows data-return oriented (`scrape_url`, `batch_scrape`, async jobs)

If file output is needed:
- use `screenshot`, `save_pdf`, `download_file`
- enforce `runtime.safe_output_root` to an isolated directory

---

## 8) Remote test suite

Set environment:

```bash
export WST_REMOTE_MCP_URL=https://your-domain/mcp
export WST_REMOTE_MCP_API_KEY=your-key
export WST_REMOTE_TARGETS=https://readyforus.app,https://claragurney.com
```

Run optional remote integration tests:

```bash
pytest -q tests/test_remote_mcp_integration.py
```

Run smoke validation script:

```bash
python verify_remote_mcp.py
```
