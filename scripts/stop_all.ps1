# Stop the whole HireSignal stack (T13): n8n, the station API, llama-server, our Ollama. Only the processes these
# scripts started are stopped (PID files in tools\; n8n = node.exe from tools\node running tools\n8n).
# Usage: powershell -ExecutionPolicy Bypass -File scripts\stop_all.ps1
$ErrorActionPreference = "Continue"
& (Join-Path $PSScriptRoot "start_n8n.ps1") -Stop
& (Join-Path $PSScriptRoot "start_stack.ps1") -Stop
& (Join-Path $PSScriptRoot "start_ollama.ps1") -Stop
foreach ($port in 5678, 8010, 8090, 11434) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { "Port $port is still in use (not started by these scripts?)" }
}
"Stopped."
