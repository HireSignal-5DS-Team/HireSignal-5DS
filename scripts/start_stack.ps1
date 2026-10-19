# Start / stop the station stack: llama-server (8090, scripts/start_llm.ps1) + station API (8010, services/api.py).
# n8n keeps its own script (scripts/start_n8n.ps1).
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\start_stack.ps1         # start both, wait until /ready
#   powershell -ExecutionPolicy Bypass -File scripts\start_stack.ps1 -Stop   # stop both (only what these scripts started)
# The API port comes from .env STATION_API_PORT (default 8010). Logs: tools/station-api.log*, PID: tools/station-api.pid.
param([switch]$Stop)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$pidFile = Join-Path $root "tools\station-api.pid"
$log = Join-Path $root "tools\station-api.log"

$port = "8010"
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) { if ($line -match '^\s*STATION_API_PORT\s*=\s*(\d+)\s*$') { $port = $Matches[1] } }
}

if ($Stop) {
    if (Test-Path $pidFile) {
        $p = Get-Process -Id (Get-Content $pidFile) -ErrorAction SilentlyContinue
        if ($p -and $p.Path -eq $python) { Stop-Process -Id $p.Id -Confirm:$false; "Stopped station API (pid $($p.Id))." }
        else { "Station API PID file is stale; nothing to stop." }
        Remove-Item $pidFile -Confirm:$false
    } else { "No station API PID file; API not started by this script." }
    & (Join-Path $PSScriptRoot "start_llm.ps1") -Stop
    exit 0
}

# 1. llama-server (skip if this script's server is already up)
$llmUp = $false
try { $llmUp = (Invoke-WebRequest "http://127.0.0.1:8090/health" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { }
if (-not $llmUp) { & (Join-Path $PSScriptRoot "start_llm.ps1") }

# 2. station API
if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { throw "Port $port is already in use" }
New-Item -ItemType Directory -Force (Join-Path $root "tools") | Out-Null
$p = Start-Process -FilePath $python -ArgumentList @("-m", "uvicorn", "services.api:app", "--host", "127.0.0.1", "--port", $port) `
        -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput $log -RedirectStandardError "$log.err"
Set-Content -Path $pidFile -Value $p.Id -Encoding ascii
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    if ($p.HasExited) { throw "station API exited (code $($p.ExitCode)); see $log.err" }
    $ok = $false
    try { $ok = (Invoke-WebRequest "http://127.0.0.1:$port/ready" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 } catch { }
    if ($ok) { "Station API ready on http://127.0.0.1:$port (pid $($p.Id)); /ready checks llama-server"; exit 0 }
}
throw "station API not ready after 60 s; see $log.err"
