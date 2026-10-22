# HireSignal V2 (document flow): Windows run guide

Target: Windows 11, RTX 4050 6 GB, 32 GB RAM, Python 3.12, the V1 setup of `RUN_LOCAL.md`.
Branch: `feature/agent-integration` (based on `release/hiresignal-v1-stable` @ `8268438`).

V2 adds the teammate's upstream agents in front of the unchanged V1 pipeline:

```
CV file (PDF/DOCX/image/TXT) or pasted text --Reader--> text + sections
    --Profile Agent (anonymise + parse, plain Qwen3-4B)--> anonymised CV text  (the Matcher's only evidence)
job paragraph --Job Agent (job-q1, plain Qwen3-4B)--> requirements (must / nice, min_years, verbatim evidence)
    --> V1: Matcher Qwen3-4B + LoRA + mandatory RAG -> validator -> Bias Auditor -> DeBERTa xsmall Judge
    --> Qwen3-0.6B Reporter -> report -> human review
```

New endpoint: `POST /api/v2/analyze`. The V1 endpoint `POST /api/v1/match` is unchanged and still works.

## Quick start (one command)

After the one-time setup below (worktree, `.v2deps`, LoRA GGUF in the V1 cache):

```powershell
.\scripts\start_v2_windows.ps1        # or double-click scripts\start_v2_windows.cmd
.\scripts\start_v2_windows.ps1 -Stop  # stop the three services
```

It starts the model server (8082), backend (8001) and frontend (5174), each in its own window, reuses any that
already answer, waits for `/ready`, and opens Chrome on `http://127.0.0.1:5174/analysis`. The V1 ports
8081/8000/5173 stay free. The model server defaults to `-NGpuLayers 8` so it can run next to a V1 LoRA server
without stopping it; with another `llama_cpp.server` running, the script refuses more than 8 GPU layers (two
fully offloaded 4B models do not fit in 6 GB). With V1 stopped, `-NGpuLayers 35` is faster. The backend runs with
`HF_HUB_OFFLINE=1` (models must already be cached). Ports, V1 folder and GPU layers are parameters
(`-ModelPort`, `-V1Repo`, ...). After a reboot, see `V2_REBOOT_RECOVERY_20261021.md`.

## 1. Keep V1 intact: use a second worktree

Run every command in PowerShell. Do not switch the V1 checkout to another branch.

```powershell
cd C:\Users\semah\HireSignal-Integration\repo
git fetch origin feature/agent-integration
git worktree add ..\repo-v2 feature/agent-integration
cd ..\repo-v2
```

The V1 folder (`repo`) keeps its branch, models, adapters and benchmark results.

## 2. Dependencies

Reuse the V1 virtual environment. The new packages are additive: they do not change the V1 packages.

```powershell
cd C:\Users\semah\HireSignal-Integration\repo-v2
..\repo\.venv\Scripts\Activate.ps1
pip install "pymupdf>=1.24" "python-docx>=1.1" "pytesseract>=0.3.10" "pillow>=10.0"
```

To leave the V1 venv untouched instead (what `start_v2_windows.ps1` expects), install them into the
Git-ignored `.v2deps` folder; the backend then needs `.v2deps` on `PYTHONPATH`, or the Reader fails with
`ModuleNotFoundError: No module named 'pymupdf'` (HTTP 422):

```powershell
..\repo\.venv\Scripts\python.exe -m pip install --target .v2deps "pymupdf>=1.24" "python-docx>=1.1" "pytesseract>=0.3.10" "pillow>=10.0"
```

Optional NER detectors for the Profile Agent (CPU, about 1.5 GB download). The rule-based anonymiser works
without them, and the V2 endpoint does not load them by default:

```powershell
pip install -r requirements-profile.txt
```

Tesseract OCR is only needed for scanned PDFs and images. Install it from the UB Mannheim build
(https://github.com/UB-Mannheim/tesseract/wiki) with the English and French language data. Then:

```powershell
$env:TESSERACT_CMD="C:\Program Files\Tesseract-OCR\tesseract.exe"
& $env:TESSERACT_CMD --version
```

Without Tesseract, text PDFs, DOCX and TXT still work. Scans then fail with a clear Reader error (HTTP 422).

## 3. One llama.cpp server on port 8081 with both models

The Profile and Job agents need the **plain** Qwen3-4B. The Matcher needs Qwen3-4B **+ LoRA**. Two servers do
not fit in 6 GB. One llama-cpp-python server can serve both aliases from a config file. It keeps only one
model in memory: on a request for the other alias it closes the current model and loads the other one
(llama-cpp-python `LlamaProxy`). Both entries use the same Q4_K_M GGUF, so no extra weights are needed.

Stop the V1 LoRA server first (Ctrl+C in its terminal). Then, in the V1 folder:

```powershell
cd C:\Users\semah\HireSignal-Integration\repo
$hub = "$PWD\.cache\hf\hub"
$gguf = "$hub\models--unsloth--Qwen3-4B-Instruct-2507-GGUF\snapshots\a06e946bb6b655725eafa393f4a9745d460374c9\Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
$lora = "$hub\models--HireSignal-5DS-Team--hiresignal-qwen3-4b-matcher-lora\snapshots\0b6925b1e3c89b6b266b10bcd30af4c6a0c2dc3a\hiresignal-lora-f16.gguf"
@{
  host = "127.0.0.1"; port = 8081
  models = @(
    @{ model = $gguf; lora_path = $lora; model_alias = "Qwen/Qwen3-4B-Instruct-2507+lora"
       n_ctx = 4096; n_gpu_layers = 35; n_threads = 4 },
    @{ model = $gguf; model_alias = "Qwen/Qwen3-4B-Instruct-2507"
       n_ctx = 6144; n_gpu_layers = 35; n_threads = 4 }
  )
} | ConvertTo-Json -Depth 4 | Set-Content -Encoding ascii ..\llama_v2.json
$env:HF_HOME="$PWD\.cache\hf"
.\.venv\Scripts\python.exe -m llama_cpp.server --config_file ..\llama_v2.json
```

The first model in the list (LoRA) loads at start, as in V1. Keep `llama_v2.json` outside the repository: it
holds local paths.

Verify (second terminal):

```powershell
curl.exe http://127.0.0.1:8081/v1/models
# both ids: Qwen/Qwen3-4B-Instruct-2507+lora and Qwen/Qwen3-4B-Instruct-2507
$body = '{"model":"Qwen/Qwen3-4B-Instruct-2507","messages":[{"role":"user","content":"Say OK."}],"max_tokens":5}'
curl.exe -s http://127.0.0.1:8081/v1/chat/completions -H "Content-Type: application/json" -d $body
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

Check with `nvidia-smi` that VRAM stays near the V1 value (about 3.1 GB) after a swap. If it grows after each
swap, use the fallback below.

Notes:
- `n_ctx` 6144 for the plain model: the Job and Profile prompts are about 1,400 tokens plus up to
  `HS_UPSTREAM_MAX_TOKENS` output tokens. With 6 GB, if loading fails, set `n_ctx` to 4096 and
  `HS_UPSTREAM_MAX_TOKENS` to 768 (verified 2026-10-17 under partial GPU offload).
- An unknown model name falls back to the first model. The backend `/ready` check compares the Matcher alias,
  and the Job Agent refuses any model name that contains "lora".
- Each candidate costs two swaps (plain for Profile and Job, then LoRA for the Matcher). On the GPU a swap is a
  few seconds.

Fallback if the config-file swap does not work on your wheel: run the V1 LoRA server on 8081 unchanged, and
start a plain server on 8080 only while you test V2 upstream agents, never both on the GPU at once
(`--n_gpu_layers 0` for the plain one keeps it on the CPU, about 10x slower).

## 4. Backend (port 8000)

```powershell
cd C:\Users\semah\HireSignal-Integration\repo-v2
..\repo\.venv\Scripts\Activate.ps1
$env:HF_HUB_OFFLINE="0"; $env:HF_HOME="..\repo\.cache\hf"
$env:HS_MATCHER_URL="http://127.0.0.1:8081/v1"
$env:HS_MATCHER_MODEL="Qwen/Qwen3-4B-Instruct-2507+lora"
$env:HS_FALLBACK="off"
$env:HS_UPSTREAM_LLM_URL="http://127.0.0.1:8081/v1"
$env:HS_UPSTREAM_LLM_MODEL="Qwen/Qwen3-4B-Instruct-2507"
$env:HS_UPSTREAM_TIMEOUT="180"
$env:HS_UPSTREAM_MAX_TOKENS="768"
$env:HS_V2_PROFILE_CHUNK_CHARS="800" # V2 integration only; teammate profile defaults remain unchanged
$env:HS_RAG="gated"
$env:HIRESIGNAL_RAG_DIR="$PWD\rag"
$env:HS_BIAS_AUDITOR="rules_v2"
$env:HS_JUDGE_MODEL="cross-encoder/nli-deberta-v3-xsmall"
$env:HS_REPORTER_SLM="on"
$env:HS_REPORTER_MODEL_PATH=(Get-ChildItem -Recurse "..\repo\.cache\hf\hub" -Filter "Qwen3-0.6B-Q8_0.gguf" | Select-Object -First 1).FullName
$env:TESSERACT_CMD="C:\Program Files\Tesseract-OCR\tesseract.exe"
$env:PYTHONPATH="$PWD;$PWD\.v2deps"  # .v2deps: V2 packages installed with pip --target (see below)
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Verify: `curl.exe http://127.0.0.1:8000/ready` returns `"ready":true`.

### API smoke test (synthetic CV of an invented person)

```powershell
$cv = Get-Content -Raw eval\profile_agent\cvs\p01_en_classic.txt
$job = "We are hiring a Machine Learning Engineer. You must have at least 2 years of professional experience building machine learning models in Python. Strong SQL skills are required. Experience with Kubernetes is a plus."
$req = @{ cv_text = $cv; job_text = $job } | ConvertTo-Json
$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v2/analyze -ContentType "application/json" -Body $req -TimeoutSec 1800
$r.stages | Format-Table stage, status, elapsed_s, error
$r.requirements | Format-Table req_id, kind, final_decision, requires_human_review
```

A file upload instead of text: `@{ cv_file_b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes("cv.pdf")); cv_file_name = "cv.pdf"; job_text = $job }`.

Expected: five stages `reader, profile, job_agent, matcher_pipeline, reporter`, all `ok`. Error codes:
- 400: bad JSON, no `job_text`, both CV inputs, bad base64;
- 413: body larger than 15 MB;
- 422: unsupported, empty or unreadable CV, or a job text with no requirement;
- 502: a model server failed; the body lists the stages that ran and the one that failed. No result is invented.

## 5. Frontend (port 5173)

```powershell
cd C:\Users\semah\HireSignal-Integration\repo-v2\frontend
npm ci
$env:VITE_EXECUTION_MODE="REAL"; $env:VITE_API_BASE_URL="http://127.0.0.1:8000"
npm run dev -- --host 127.0.0.1 --port 5173
```

Use the same `VITE_EXECUTION_MODE` / `VITE_API_BASE_URL` values as your V1 `.env.local`, if you have one. REAL mode
now calls `/api/v2/analyze`: an uploaded file goes to the server Reader, pasted text goes as `cv_text`, and the
job description paragraph goes as `job_text`. Each candidate shows "Pipeline stages (actual)" from the server.
`VITE_API_FLOW=v1` restores the old structured `/api/v1/match` flow.

## 6. Tests

```powershell
cd C:\Users\semah\HireSignal-Integration\repo-v2
python -m pytest -q integration matcher tests\test_*.py      # mock suites, no GPU needed
cd frontend; npm test; npx tsc -b
```

GPU tests still to run on this machine (not run in the cloud):
1. The single-port swap with `n_gpu_layers 35`, checked with `nvidia-smi`.
2. The API smoke test above, with a PDF, a DOCX and a scanned image.
3. The frontend: upload a PDF, paste a job paragraph, run, and check the stage list and HUMAN REVIEW flags.

Report the commit, `nvidia-smi` output after a swap, the `stages` table, and the per-requirement table.
