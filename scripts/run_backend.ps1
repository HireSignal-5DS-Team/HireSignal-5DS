<#
  Launch the FastAPI backend. Loads backend/.env, points reporter GGUF to the cached file.
  Usage: pwsh ./scripts/run_backend.ps1 [-Port 8000]
#>
param(
    [int]$Port = 8000,
    [string]$Host_ = "127.0.0.1"
)
$ErrorActionPreference = "Stop"
$repo = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repo

$cache = Join-Path $repo ".cache"
$hf = Join-Path $cache "hf"
$env:HF_HOME = $hf
$env:HF_HUB_OFFLINE = "0"
$env:PYTHONPATH = "$repo;$($env:PYTHONPATH)"

Get-Content (Join-Path $repo "backend/.env") | ForEach-Object {
    if ($_ -match "^\s*([A-Z_][A-Z0-9_]*)=(.*)$") {
        Set-Item -Path "env:$($matches[1])" -Value $matches[2]
    }
}
# Absolute RAG dir (overriding relative in .env)
$env:HIRESIGNAL_RAG_DIR = Join-Path $repo "rag"

# Locate the Reporter GGUF
$rep = Get-ChildItem -Path (Join-Path $hf "hub") -Recurse -ErrorAction SilentlyContinue -Filter "Qwen3-0.6B-Q8_0.gguf" | Select-Object -First 1
if ($rep) {
    $env:HS_REPORTER_MODEL_PATH = $rep.FullName
    Write-Host "[run_backend] reporter model: $($rep.FullName)"
} else {
    Write-Host "[run_backend] WARNING: Qwen3-0.6B-Q8_0.gguf not found; reporter will fall back to deterministic"
    $env:HS_REPORTER_SLM = "off"
}

Write-Host "[run_backend] starting uvicorn on http://${Host_}:${Port}"
& "$repo\.venv\Scripts\python.exe" -m uvicorn backend.main:app --host $Host_ --port $Port
