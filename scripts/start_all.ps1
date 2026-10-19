# Start the whole HireSignal stack in order, with health checks (T13):
#   1. Ollama (our server, models in models\ollama; the Ollama desktop app must be closed)   :11434
#   2. llama-server (Qwen3-4B + Matcher LoRA)                                                 :8090
#   3. station API (FastAPI, waits until /ready sees llama-server)                            :8010
#   4. n8n (portable Node, data in .n8n\; webhook needs X-HireSignal-Token = WEBHOOK_TOKEN)    :5678
# Logs: tools\*.log. Stop everything with scripts\stop_all.ps1. Nothing global is changed.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\start_all.ps1 [-NoOllama]
param([switch]$NoOllama)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Wait-Url($url, $name, $seconds) {
    for ($i = 0; $i -lt $seconds; $i++) {
        try { if ((Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) { "$name ready ($url)"; return } } catch { }
        Start-Sleep -Seconds 1
    }
    throw "$name not ready after $seconds s ($url); see the logs in tools\"
}

# 1. Ollama (vision path of the Reader; READER_MODE=late falls back to OCR with a warning if it is missing)
if (-not $NoOllama) {
    if (Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue) {
        $owner = (Get-Process -Id (Get-NetTCPConnection -LocalPort 11434 -State Listen)[0].OwningProcess).Path
        "Port 11434 already in use by $owner (if it is the Ollama desktop app, quit it: its models are not in models\ollama)."
    } else {
        & (Join-Path $PSScriptRoot "start_ollama.ps1")
    }
    Wait-Url "http://127.0.0.1:11434/api/version" "Ollama" 30
}

# 2 + 3. llama-server and the station API
& (Join-Path $PSScriptRoot "start_stack.ps1")
Wait-Url "http://127.0.0.1:8010/ready" "station API" 120

# 4. n8n, in the background (start_n8n.ps1 runs in the foreground: start it hidden with its own log)
if (Get-NetTCPConnection -LocalPort 5678 -State Listen -ErrorAction SilentlyContinue) {
    "n8n already listening on 5678"
} else {
    $log = Join-Path $root "tools\n8n.log"
    Start-Process -FilePath "powershell.exe" -ArgumentList @("-ExecutionPolicy", "Bypass", "-File",
        (Join-Path $PSScriptRoot "start_n8n.ps1")) -WindowStyle Hidden -RedirectStandardOutput $log `
        -RedirectStandardError "$log.err" | Out-Null
    Wait-Url "http://127.0.0.1:5678/healthz" "n8n" 120
}
"All up. Editor: http://localhost:5678  Webhook: POST http://127.0.0.1:5678/webhook/hiresignal (header X-HireSignal-Token)"
