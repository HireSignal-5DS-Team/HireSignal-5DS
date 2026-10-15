# HireSignal Matcher benchmark queue for a Windows laptop with an NVIDIA GPU (tested target: RTX 4050 6 GB).
# Runs ONE model at a time (6 GB VRAM). Every run is resumable: re-run this script after an interruption.
# Usage (PowerShell, from the repo root, venv activated):  .\scripts\run_benchmark_windows.ps1 [-Device cuda] [-Split val]
param([string]$Device = "cuda", [string]$Split = "val", [string]$Dtype = "float32")
$ErrorActionPreference = "Stop"

if (-not $env:HIRESIGNAL_RAG_DIR) { $env:HIRESIGNAL_RAG_DIR = (Resolve-Path "..\HireSignal-rag\rag").Path }
if (-not (Test-Path "$env:HIRESIGNAL_RAG_DIR\retrieval.py")) { throw "RAG code not found; see docs/WINDOWS_LOCAL_BENCHMARK.md step 2" }
if ($Split -eq "test") { throw "test split is LOCKED; run it by hand with --i-understand-test-is-locked for the selected config only" }

$runs = @(
  @("qwen2.5-0.5b",              "--model", "Qwen/Qwen2.5-0.5B-Instruct", "--revision", "7ae557604adf67be50417f59c2c2f167def9a775"),
  @("qwen2.5-0.5b+kushal-lora",  "--model", "Qwen/Qwen2.5-0.5B-Instruct", "--revision", "7ae557604adf67be50417f59c2c2f167def9a775",
                                 "--adapter", "Kus-hal/resume-screener-lora", "--adapter-revision", "e4c042f538b4a899b9aa2f2d38bbc39d27fb7aa6"),
  @("qwen3-0.6b",                "--model", "Qwen/Qwen3-0.6B", "--revision", "c1899de289a04d12100db370d81485cdf75e47ca"),
  @("smollm2-360m",              "--model", "HuggingFaceTB/SmolLM2-360M-Instruct", "--revision", "a10cc1512eabd3dde888204e902eca88bddb4951")
)
python -m benchmark.run --backend lexical --split $Split --knowledge rag --run-id "lexical-rag-$Split"
foreach ($r in $runs) {
  $id = "$($r[0])-rag-$Split-$Device"
  Write-Host "=== $(Get-Date -Format HH:mm:ss) $id"
  python -m benchmark.run --backend transformers @($r[1..($r.Length - 1)]) --split $Split --knowledge rag `
    --device $Device --dtype $Dtype --run-id $id
  if ($LASTEXITCODE -ne 0) { throw "run $id failed" }
}
python -m benchmark.compare --split $Split
