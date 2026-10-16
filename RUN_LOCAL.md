# HireSignal — local run (Windows, RTX 4050 6 GB)

## Processes (one terminal each)

### 1) Matcher LoRA server — port 8081 (GPU)
```powershell
cd C:\Users\semah\HireSignal-Integration\repo
$env:HF_HUB_OFFLINE="0"; $env:HF_HOME="$PWD\.cache\hf"
.\.venv\Scripts\python.exe -m llama_cpp.server `
  --model ".cache\hf\hub\models--unsloth--Qwen3-4B-Instruct-2507-GGUF\snapshots\a06e946bb6b655725eafa393f4a9745d460374c9\Qwen3-4B-Instruct-2507-Q4_K_M.gguf" `
  --lora_path ".cache\hf\hub\models--HireSignal-5DS-Team--hiresignal-qwen3-4b-matcher-lora\snapshots\0b6925b1e3c89b6b266b10bcd30af4c6a0c2dc3a\hiresignal-lora-f16.gguf" `
  --model_alias "Qwen/Qwen3-4B-Instruct-2507+lora" `
  --n_ctx 2048 --n_gpu_layers 35 --n_threads 4 `
  --host 127.0.0.1 --port 8081
```
Verify: `curl http://127.0.0.1:8081/v1/models`

### 2) FastAPI backend — port 8000
```powershell
cd C:\Users\semah\HireSignal-Integration\repo
.\.venv\Scripts\Activate.ps1
$env:HF_HUB_OFFLINE="0"; $env:HF_HOME="$PWD\.cache\hf"
$env:HS_MATCHER_URL="http://127.0.0.1:8081/v1"
$env:HS_MATCHER_MODEL="Qwen/Qwen3-4B-Instruct-2507+lora"
$env:HS_FALLBACK="off"
$env:HS_RAG="gated"
$env:HIRESIGNAL_RAG_DIR="$PWD\rag"
$env:HS_BIAS_AUDITOR="rules_v2"
$env:HS_JUDGE_MODEL="cross-encoder/nli-deberta-v3-xsmall"
$env:HS_REPORTER_SLM="on"
$env:HS_REPORTER_MODEL_PATH=(Get-ChildItem -Recurse ".cache\hf\hub" -Filter "Qwen3-0.6B-Q8_0.gguf" | Select-Object -First 1).FullName
$env:PYTHONPATH="$PWD"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
Verify: `curl http://127.0.0.1:8000/ready` → `{"ready":true,...}`

### 3) Frontend (Vite) — port 5173
```powershell
cd C:\Users\semah\HireSignal-Integration\repo\frontend
npm run dev -- --host 127.0.0.1 --port 5173
```
Browser: http://127.0.0.1:5173/analysis

## Verified end-to-end (2026-10-16)

- Matcher: `Qwen/Qwen3-4B-Instruct-2507+lora@0b6925b1`, Q4_K_M + f16 LoRA
- Knowledge: `rag.gated.v1+bm25` (ESCO + USAJOBS, bundled in `./rag`)
- Bias: `rules_v2`
- Judge: `cross-encoder/nli-deberta-v3-xsmall@a1508764`
- Reporter: `Qwen3-0.6B-Q8_0` (optional, deterministic fallback)
- Latency on this box: ~3.8 s per 3-requirement match, model warm. VRAM ≈ 3.1 GB / 6.0 GB.
- Reference `integration/examples/cv.json + job.json`: r1 MET (Java), r2 MET (SQL), r3 MISSING (Kubernetes). Judge r1 FAIL, r2 UNCERTAIN → both flagged HUMAN REVIEW (expected: NLI can't do year arithmetic).

## Deviations from pinned config (documented)

- `llama-cpp-python==0.3.22` (cu125 wheel) in place of the pinned `0.3.16` — no prebuilt 0.3.16 Win+py312 wheel exists on PyPI or the CUDA index. Server CLI identical.
- `convert_lora_to_gguf.py` taken from llama.cpp tag `b5116` to match the installed `gguf==0.19.0`.
- CUDA runtime shipped in-venv via `nvidia-cuda-runtime-cu12 / nvidia-cublas-cu12 / nvidia-cuda-nvrtc-cu12`; preload done by `_hiresignal_cuda_dllpath.pth`.
- No fallback (base) Matcher server: VRAM budget. Set `HS_FALLBACK=off`.
- No Qdrant: BM25 (`HS_RAG=gated`) is the verified default on the AI branch.
