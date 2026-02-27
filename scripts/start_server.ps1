$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeDir = Join-Path $RootDir ".runtime"
$PidFile = Join-Path $RuntimeDir "web_scraper_mcp.pid"
$LogFile = Join-Path $RuntimeDir "web_scraper_mcp.log"
$ErrLogFile = Join-Path $RuntimeDir "web_scraper_mcp.err.log"

$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$Transport = if ($env:WST_SERVER_TRANSPORT) { $env:WST_SERVER_TRANSPORT } else { "streamable-http" }
$HostName = if ($env:WST_SERVER_HOST) { $env:WST_SERVER_HOST } else { "0.0.0.0" }
$PortValue = if ($env:WST_SERVER_PORT) { $env:WST_SERVER_PORT } else { "8000" }
$McpPath = if ($env:WST_SERVER_PATH) { $env:WST_SERVER_PATH } else { "/mcp" }
$ConfigPath = if ($env:WST_CONFIG_JSON) { $env:WST_CONFIG_JSON } else { (Join-Path $RootDir "config.json") }
$LocalConfigPath = if ($env:WST_LOCAL_CFG) { $env:WST_LOCAL_CFG } else { (Join-Path $RootDir "settings.local.cfg") }

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

if (Test-Path $PidFile) {
    $ExistingPid = Get-Content $PidFile -Raw
    $ExistingPid = $ExistingPid.Trim()
    if ($ExistingPid) {
        $existingProc = Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue
        if ($existingProc) {
            Write-Host "MCP server already running (pid=$ExistingPid)."
            exit 0
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

$argList = @(
    "-m", "web_scraper_toolkit.server.mcp_server",
    "--transport", $Transport,
    "--host", $HostName,
    "--port", $PortValue,
    "--path", $McpPath,
    "--config", $ConfigPath
)

if (Test-Path $LocalConfigPath) {
    $argList += @("--local-config", $LocalConfigPath)
}

$process = Start-Process `
    -FilePath $PythonBin `
    -ArgumentList $argList `
    -WorkingDirectory $RootDir `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError $ErrLogFile `
    -PassThru

Start-Sleep -Seconds 2

if ($process.HasExited) {
    Write-Error "Failed to start MCP server. See $LogFile and $ErrLogFile"
}

$process.Id | Out-File -FilePath $PidFile -Encoding ascii -Force

$healthUrl = "http://127.0.0.1:$PortValue$McpPath"
$healthArgs = @("$RootDir/scripts/healthcheck_mcp.py", "--url", $healthUrl)
if ($env:WST_MCP_API_KEY) {
    $healthArgs += @("--api-key", $env:WST_MCP_API_KEY)
}

& $PythonBin $healthArgs *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "MCP server started (pid=$($process.Id)) but health check failed. URL: $healthUrl"
    exit 1
}

Write-Host "MCP server started (pid=$($process.Id)) and passed health check."
