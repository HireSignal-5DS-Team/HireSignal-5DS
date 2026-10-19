# Start / stop the local LLM server: llama.cpp llama-server (tools/llama.cpp) with ONE Qwen3-4B Q4_K_M base
# and the Matcher LoRA loaded but not applied. Callers pick the adapter per request:
#   "lora": [{"id": 0, "scale": 0}]  -> plain Qwen3-4B (Profile, Job Agent)
#   "lora": [{"id": 0, "scale": 1}]  -> Matcher (base + LoRA)
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\start_llm.ps1          # start (background), wait until healthy
#   powershell -ExecutionPolicy Bypass -File scripts\start_llm.ps1 -Stop    # stop the server started by this script
#   powershell -ExecutionPolicy Bypass -File scripts\start_llm.ps1 -NoLora  # plain model only (parity checks)
# Settings come from .env (LLM_PORT, LLM_MODEL, LLM_MODEL_FILE, LLM_LORA_FILE, LLM_GPU_LAYERS, LLM_CTX).
param([switch]$Stop, [switch]$NoLora)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root "tools\llama.cpp\llama-server.exe"
$pidFile = Join-Path $root "tools\llama-server.pid"
$log = Join-Path $root "tools\llama-server.log"

$cfg = @{ LLM_PORT = "8090"; LLM_MODEL = "qwen3-4b"; LLM_MODEL_FILE = "models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf";
          LLM_LORA_FILE = "models/hiresignal-lora-f16.gguf"; LLM_GPU_LAYERS = "all"; LLM_CTX = "4096" }
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^\s*(LLM_[A-Z_]+)\s*=\s*(.*?)\s*$' -and $cfg.ContainsKey($Matches[1])) { $cfg[$Matches[1]] = $Matches[2] }
    }
}

if ($Stop) {
    if (-not (Test-Path $pidFile)) { "No PID file; server not started by this script."; exit 0 }
    $p = Get-Process -Id (Get-Content $pidFile) -ErrorAction SilentlyContinue
    if ($p -and $p.Path -eq $exe) { Stop-Process -Id $p.Id -Confirm:$false; "Stopped llama-server (pid $($p.Id))." }
    else { "PID file is stale; nothing to stop." }
    Remove-Item $pidFile -Confirm:$false
    exit 0
}

if (-not (Test-Path $exe)) { throw "llama-server not found in tools\llama.cpp (see tasks/T02b_report.md)" }
$port = $cfg.LLM_PORT
if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { throw "Port $port is already in use" }

# Sampling is set per request by the callers (V2 values: temperature 0, top_p 1, seed 0, repeat_penalty 1.1).
$serverArgs = @("--model", (Join-Path $root $cfg.LLM_MODEL_FILE), "--alias", $cfg.LLM_MODEL,
                "--host", "127.0.0.1", "--port", $port, "--ctx-size", $cfg.LLM_CTX,
                "--n-gpu-layers", $cfg.LLM_GPU_LAYERS, "--parallel", "1", "--no-webui")
if (-not $NoLora) { $serverArgs += @("--lora", (Join-Path $root $cfg.LLM_LORA_FILE), "--lora-init-without-apply") }

$p = Start-Process -FilePath $exe -ArgumentList $serverArgs -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $log -RedirectStandardError "$log.err"
Set-Content -Path $pidFile -Value $p.Id -Encoding ascii
for ($i = 0; $i -lt 120; $i++) {
    Start-Sleep -Seconds 1
    if ($p.HasExited) { throw "llama-server exited (code $($p.ExitCode)); see $log.err" }
    $ok = $false
    try { $ok = (Invoke-WebRequest "http://127.0.0.1:$port/health" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { }
    if ($ok) {
        if (-not $NoLora) {
            # b11139: --lora-init-without-apply still reports scale 1 and applies it to requests without a "lora"
            # field (measured, tasks/T02b_report.md). Force the global default to 0 = plain model.
            Invoke-RestMethod "http://127.0.0.1:$port/lora-adapters" -Method Post -ContentType "application/json" `
                -Body '[{"id": 0, "scale": 0.0}]' | Out-Null
        }
        "llama-server ready on http://127.0.0.1:$port (pid $($p.Id), lora loaded: $(-not $NoLora), default scale 0)"; exit 0
    }
}
throw "llama-server not healthy after 120 s; see $log.err"
