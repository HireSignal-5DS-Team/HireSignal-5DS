<#
  One-command local start of HireSignal V2 on Windows (docs/integration/V2_WINDOWS_RUN.md).
  Starts, each in its own PowerShell window, unless already healthy:
    1. llama.cpp server, one port, two aliases (Qwen3-4B + LoRA for the Matcher, plain Qwen3-4B for Profile/Job)
    2. FastAPI backend (/api/v2/analyze)
    3. Vite frontend in REAL mode
  then opens Chrome on the analysis page.

  Uses the V1 virtual environment and model cache read-only (..\..\repo by default) and the V2-only
  packages in .v2deps\ via PYTHONPATH. Default ports 8082/8001/5174 leave the V1 ports 8081/8000/5173 free.

  Usage:
    .\scripts\start_v2_windows.ps1              # start (or reuse) all three, open Chrome
    .\scripts\start_v2_windows.ps1 -Stop        # stop the three services on these ports
    .\scripts\start_v2_windows.ps1 -NoBrowser
#>
param(
    [int]$ModelPort = 8082,
    [int]$BackendPort = 8001,
    [int]$FrontendPort = 5174,
    [string]$V1Repo = (Join-Path $PSScriptRoot "..\..\repo"),
    [int]$NGpuLayers = 8,
    [switch]$Stop,
    [switch]$NoBrowser
)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ports = @($ModelPort, $BackendPort, $FrontendPort)

function Stop-Port([int]$port) {
    $pids = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($p in $pids) {
        Write-Host "[start_v2] stopping PID $p on port $port"
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
    }
}

if ($Stop) { $ports | ForEach-Object { Stop-Port $_ }; return }

function Test-Url([string]$url) {
    try { Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 5 | Out-Null; return $true } catch { return $false }
}

function Wait-Url([string]$url, [string]$name, [int]$timeoutSec) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-Url $url) { Write-Host "[start_v2] $name up: $url"; return }
        Start-Sleep -Seconds 3
    }
    throw "$name did not answer at $url within ${timeoutSec}s; read its window for the error"
}

function Quote([string]$s) { "'" + $s.Replace("'", "''") + "'" }

# -EncodedCommand avoids quoting problems with paths in the new window's command line.
function Start-InWindow([string]$title, [string]$workDir, [hashtable]$envs, [string]$command) {
    $lines = @("`$Host.UI.RawUI.WindowTitle = $(Quote $title)", "Set-Location $(Quote $workDir)")
    $lines += $envs.GetEnumerator() | ForEach-Object { "`$env:$($_.Key) = $(Quote $_.Value)" }
    $lines += $command
    $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($lines -join "`n"))
    Start-Process powershell.exe -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $enc | Out-Null
}

$v1 = (Resolve-Path $V1Repo).Path
$py = Join-Path $v1 ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "V1 virtual environment not found: $py (pass -V1Repo)" }
$hf = Join-Path $v1 ".cache\hf"

function Find-OneFile([string]$name) {
    $m = Get-ChildItem -Path (Join-Path $hf "hub") -Recurse -Filter $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $m) { throw "model file not found: $name under $hf\hub" }
    return $m.FullName
}

# 1. Model server
$modelUrl = "http://127.0.0.1:$ModelPort/v1"
if (Test-Url "$modelUrl/models") {
    Write-Host "[start_v2] reusing model server on $ModelPort"
} else {
    $other = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*llama_cpp.server*" }
    if ($other) {
        # Separate model servers were tested with 8 GPU layers in V2 while V1 remained active.
        # Never require shutting down the working V1 to launch V2.
        if ($NGpuLayers -gt 8) {
            throw "A separate llama.cpp server is running. Use -NGpuLayers 8 or lower to protect the available VRAM; V1 remains untouched."
        }
        Write-Host "[start_v2] another model server is running; keeping it untouched and using $NGpuLayers GPU layers for V2"
    }
    $gguf = Find-OneFile "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
    $lora = Find-OneFile "hiresignal-lora-f16.gguf"
    # Config holds local paths: keep it outside the repository.
    $cfg = Join-Path (Split-Path $repo) "llama_v2_$ModelPort.json"
    @{
        host = "127.0.0.1"; port = $ModelPort
        models = @(
            @{ model = $gguf; lora_path = $lora; model_alias = "Qwen/Qwen3-4B-Instruct-2507+lora"
               n_ctx = 4096; n_gpu_layers = $NGpuLayers; n_threads = 4 },
            @{ model = $gguf; model_alias = "Qwen/Qwen3-4B-Instruct-2507"
               n_ctx = 6144; n_gpu_layers = $NGpuLayers; n_threads = 4 }
        )
    } | ConvertTo-Json -Depth 4 | Set-Content -Encoding ascii $cfg
    Write-Host "[start_v2] starting model server on $ModelPort ($cfg)"
    Start-InWindow "HireSignal V2 model server :$ModelPort" $v1 @{ HF_HOME = $hf } `
        "& $(Quote $py) -m llama_cpp.server --config_file $(Quote $cfg)"
    Wait-Url "$modelUrl/models" "model server" 300
}

# 2. Backend
$backendUrl = "http://127.0.0.1:$BackendPort"
if (Test-Url "$backendUrl/health") {
    Write-Host "[start_v2] reusing backend on $BackendPort"
} else {
    $envs = @{
        HF_HOME = $hf; HF_HUB_OFFLINE = "1"
        HS_MATCHER_URL = $modelUrl; HS_MATCHER_MODEL = "Qwen/Qwen3-4B-Instruct-2507+lora"
        HS_FALLBACK = "off"
        HS_UPSTREAM_LLM_URL = $modelUrl; HS_UPSTREAM_LLM_MODEL = "Qwen/Qwen3-4B-Instruct-2507"
        HS_UPSTREAM_TIMEOUT = "180"; HS_UPSTREAM_MAX_TOKENS = "768"; HS_V2_PROFILE_CHUNK_CHARS = "800"
        HS_RAG = "gated"; HIRESIGNAL_RAG_DIR = (Join-Path $repo "rag")
        HS_BIAS_AUDITOR = "rules_v2"; HS_JUDGE_MODEL = "cross-encoder/nli-deberta-v3-xsmall"
        HS_REPORTER_SLM = "on"; HS_REPORTER_MODEL_PATH = (Find-OneFile "Qwen3-0.6B-Q8_0.gguf")
        PYTHONPATH = "$repo;$(Join-Path $repo '.v2deps')"
    }
    $tess = "C:\Program Files\Tesseract-OCR\tesseract.exe"
    if (Test-Path $tess) { $envs.TESSERACT_CMD = $tess }
    else { Write-Host "[start_v2] Tesseract not installed: scanned PDFs/images will return HTTP 422; text PDF/DOCX/TXT work" }
    Write-Host "[start_v2] starting backend on $BackendPort"
    Start-InWindow "HireSignal V2 backend :$BackendPort" $repo $envs `
        "& $(Quote $py) -m uvicorn backend.main:app --host 127.0.0.1 --port $BackendPort"
    Wait-Url "$backendUrl/health" "backend" 300
}
$ready = Invoke-RestMethod "$backendUrl/ready" -TimeoutSec 300
if (-not $ready.ready) { throw "backend not ready: $($ready.checks | ConvertTo-Json -Compress)" }
Write-Host "[start_v2] backend ready (matcher, pipeline, rag_dir ok)"

# 3. Frontend
$frontendUrl = "http://127.0.0.1:$FrontendPort"
if (Test-Url $frontendUrl) {
    Write-Host "[start_v2] reusing frontend on $FrontendPort"
} else {
    $fe = Join-Path $repo "frontend"
    if (-not (Test-Path (Join-Path $fe "node_modules"))) {
        Write-Host "[start_v2] installing frontend dependencies (npm ci)"
        Push-Location $fe; try { npm ci; if ($LASTEXITCODE -ne 0) { throw "npm ci failed" } } finally { Pop-Location }
    }
    Write-Host "[start_v2] starting frontend on $FrontendPort"
    Start-InWindow "HireSignal V2 frontend :$FrontendPort" $fe `
        @{ VITE_EXECUTION_MODE = "REAL"; VITE_API_BASE_URL = $backendUrl; VITE_API_FLOW = "v2" } `
        "npm run dev -- --port $FrontendPort --strictPort"
    Wait-Url $frontendUrl "frontend" 120
}

$app = "$frontendUrl/analysis"
Write-Host "[start_v2] HireSignal V2 running: $app"
if (-not $NoBrowser) {
    $chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
                "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
                "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($chrome) { Start-Process $chrome $app } else { Start-Process $app }
}
