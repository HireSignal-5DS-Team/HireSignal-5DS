# Start the local n8n (portable Node in tools/node, n8n in tools/n8n, data in .n8n/).
# Usage: powershell -ExecutionPolicy Bypass -File scripts\start_n8n.ps1          # start (foreground)
#        powershell -ExecutionPolicy Bypass -File scripts\start_n8n.ps1 -Stop    # stop the n8n started from tools\n8n
# Nothing global is changed: PATH is set for this process only.
param([switch]$Stop)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$node = Join-Path $root "tools\node"
$n8n = Join-Path $root "tools\n8n\node_modules\n8n\bin\n8n"
$port = if ($env:N8N_PORT) { $env:N8N_PORT } else { "5678" }

if ($Stop) {
    # only node.exe processes from tools\node whose command line runs our tools\n8n (n8n main + its task runners)
    $procs = Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" |
        Where-Object { $_.ExecutablePath -eq (Join-Path $node "node.exe") -and $_.CommandLine -like "*tools\n8n*" }
    if (-not $procs) { "n8n is not running."; exit 0 }
    foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -Confirm:$false -ErrorAction SilentlyContinue; "Stopped n8n process (pid $($p.ProcessId))." }
    exit 0
}

if (-not (Test-Path (Join-Path $node "node.exe"))) { throw "Portable Node not found in $node (see tasks/T02_report.md)" }
if (-not (Test-Path $n8n)) { throw "n8n not found in tools\n8n (see tasks/T02_report.md)" }
if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { throw "Port $port is already in use" }

$env:PATH = "$node;$env:PATH"
$env:N8N_USER_FOLDER = $root          # n8n stores its data in <N8N_USER_FOLDER>\.n8n
$env:N8N_PORT = $port
$env:N8N_HOST = "localhost"
$env:N8N_LISTEN_ADDRESS = "127.0.0.1" # local only
# Read/Write Files nodes (manual demo, error log, T08 outbox files) may only touch these three folders.
# n8n runs from the repo root, so the workflows use relative paths (no user path inside the workflow JSON).
New-Item -ItemType Directory -Force (Join-Path $root "eval\logs"), (Join-Path $root "eval\outbox\invite"), (Join-Path $root "eval\outbox\reject") | Out-Null  # n8n needs the folders to exist
$env:N8N_RESTRICT_FILE_ACCESS_TO = "$(Join-Path $root 'data\processed');$(Join-Path $root 'eval\logs');$(Join-Path $root 'eval\outbox')"
$env:N8N_DIAGNOSTICS_ENABLED = "false" # no telemetry
# Known n8n 2.43 + SQLite workaround (accepted by the Brain in T06). n8n 2.43 publication outbox on SQLite: a record left "in_progress" by a shutdown is never reclaimed, so the
# workflow never activates (seen in T05). The classic activation path activates every published workflow at start.
$env:N8N_USE_WORKFLOW_PUBLICATION_SERVICE = "false"
# Delete stored executions (and their uploaded CV files) after 14 days. These equal n8n 2.43's defaults; set
# explicitly so the policy is visible and survives an n8n upgrade (T06).
$env:EXECUTIONS_DATA_PRUNE = "true"
$env:EXECUTIONS_DATA_MAX_AGE = "336"
# T13: the webhook needs the header X-HireSignal-Token = WEBHOOK_TOKEN (from .env, git-ignored; never printed). The
# "Check token" node reads it with $env, so env access in expressions is allowed for this process only.
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) { if ($line -match '^\s*WEBHOOK_TOKEN\s*=\s*(\S+)\s*$') { $env:WEBHOOK_TOKEN = $Matches[1] } }
}
if (-not $env:WEBHOOK_TOKEN) { Write-Warning "WEBHOOK_TOKEN is not set in .env: every webhook request will be refused (403)." }
$env:N8N_BLOCK_ENV_ACCESS_IN_NODE = "false"
Set-Location $root

& (Join-Path $node "node.exe") $n8n start
