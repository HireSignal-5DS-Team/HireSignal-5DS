<#
  Serve Qwen3-4B-Instruct-2507 + HireSignal LoRA via llama-cpp-python OpenAI server.
  Converts the PEFT adapter to GGUF (f16) on first run, then launches on port 8081 with GPU offload.

  Usage:
    pwsh ./scripts/serve_matcher_lora.ps1 [-Port 8081] [-NGpuLayers 35] [-NCtx 2048]
#>
param(
    [int]$Port = 8081,
    [int]$NGpuLayers = 35,
    [int]$NCtx = 2048,
    [int]$NThreads = 6
)
$ErrorActionPreference = "Stop"
$repo = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repo

$cache = Join-Path $repo ".cache"
$hf = Join-Path $cache "hf"
$models = Join-Path $cache "hs_models"
$env:HF_HOME = $hf
$env:HF_HUB_OFFLINE = "0"

# Locate the three HF-cached pieces by scanning the snapshot tree
function Find-OneFile([string]$glob) {
    $m = Get-ChildItem -Path (Join-Path $hf "hub") -Recurse -ErrorAction SilentlyContinue -Filter $glob | Select-Object -First 1
    if (-not $m) { throw "not found: $glob under $hf" }
    return $m.FullName
}

$baseGguf   = Find-OneFile "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
$adapterCfg = Find-OneFile "adapter_config.json"
$adapterDir = Split-Path $adapterCfg
$baseConfig = Find-OneFile "config.json"            # first config.json we find — should be the Qwen3-4B base
$baseHf     = Split-Path $baseConfig

$loraGguf = Join-Path $adapterDir "hiresignal-lora-f16.gguf"
if (-not (Test-Path $loraGguf)) {
    Write-Host "[serve_matcher_lora] converting LoRA adapter to GGUF (f16) ..."
    & "$repo\.venv\Scripts\python.exe" "$repo\.cache\scripts\convert_lora_to_gguf.py" `
        "$adapterDir" --base "$baseHf" --outtype f16 --outfile "$loraGguf"
    if ($LASTEXITCODE -ne 0) { throw "convert_lora_to_gguf failed ($LASTEXITCODE)" }
} else {
    Write-Host "[serve_matcher_lora] reusing existing $loraGguf"
}

Write-Host "[serve_matcher_lora] starting llama_cpp.server on 127.0.0.1:$Port (n_gpu_layers=$NGpuLayers, n_ctx=$NCtx)"
& "$repo\.venv\Scripts\python.exe" -m llama_cpp.server `
    --model "$baseGguf" `
    --lora_path "$loraGguf" `
    --model_alias "Qwen/Qwen3-4B-Instruct-2507+lora" `
    --n_ctx $NCtx `
    --n_gpu_layers $NGpuLayers `
    --n_threads $NThreads `
    --host 127.0.0.1 `
    --port $Port
