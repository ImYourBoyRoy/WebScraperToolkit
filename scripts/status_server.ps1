$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PidFile = Join-Path $RootDir ".runtime/web_scraper_mcp.pid"
$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$PortValue = if ($env:WST_SERVER_PORT) { $env:WST_SERVER_PORT } else { "8000" }
$McpPath = if ($env:WST_SERVER_PATH) { $env:WST_SERVER_PATH } else { "/mcp" }

if (-not (Test-Path $PidFile)) {
    Write-Host "MCP server is not running (pid file missing)."
    exit 1
}

$pidValue = (Get-Content $PidFile -Raw).Trim()
if (-not $pidValue) {
    Write-Host "MCP server is not running (invalid pid file)."
    exit 1
}

$proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
if (-not $proc) {
    Write-Host "MCP server is not running (stale pid=$pidValue)."
    exit 1
}

Write-Host "MCP server process is running (pid=$pidValue)."

$healthUrl = "http://127.0.0.1:$PortValue$McpPath"
$healthArgs = @("$RootDir/scripts/healthcheck_mcp.py", "--url", $healthUrl)
if ($env:WST_MCP_API_KEY) {
    $healthArgs += @("--api-key", $env:WST_MCP_API_KEY)
}

& $PythonBin $healthArgs *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Health check: OK ($healthUrl)"
    exit 0
}

Write-Host "Health check: FAILED ($healthUrl)"
exit 2
