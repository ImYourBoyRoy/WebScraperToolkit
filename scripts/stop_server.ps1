$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PidFile = Join-Path $RootDir ".runtime/web_scraper_mcp.pid"

if (-not (Test-Path $PidFile)) {
    Write-Host "MCP server pid file not found. Nothing to stop."
    exit 0
}

$pidValue = (Get-Content $PidFile -Raw).Trim()
if (-not $pidValue) {
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "Invalid pid file. Cleaned up."
    exit 0
}

$proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
if (-not $proc) {
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "Process not found. Cleaned stale pid file."
    exit 0
}

Write-Host "Stopping MCP server (pid=$pidValue)..."
Stop-Process -Id $pidValue -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

$stillRunning = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
if ($stillRunning) {
    Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
}

Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
Write-Host "MCP server stopped."
