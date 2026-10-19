# Install and run HireSignal (Windows 11, from zero)

Everything is local and free. Tested on Windows 11 with an RTX 4050 Laptop GPU (6 GB) and 32 GB RAM. Nothing global
is changed except the tools you install yourself in steps 1–3 (Python, Git, Tesseract, Ollama). Ports used: n8n 5678,
station API 8010, llama-server 8090, Ollama 11434.

## 0. Prerequisites

| what | version used | why |
|---|---|---|
| Windows 11 x64 + NVIDIA driver with CUDA 12.x support | driver 581.86 | llama-server (CUDA 12.4 build) and PyTorch cu126 |
| Python | 3.12 | the station API, evaluation scripts, tests |
| Git (optional) | any | to clone the repo |
| ~25 GB free disk | | models (~4 GB for the production set, +~9 GB for the benchmark-only models), llama.cpp, Node, n8n |

## 1. Python environment

```powershell
cd <repo folder>
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt     # torch cu126 comes from the PyTorch index in the file
.venv\Scripts\python -m pip check                           # must say: No broken requirements found.
```

Data-prep scripts only: `pip install -r requirements-dataprep.txt`. On Windows with Smart App Control, pyarrow may
be blocked; the app itself does not need it.

## 2. Tesseract OCR (Reader, path 1)

1. Download the UB Mannheim Windows installer of Tesseract 5 (github.com/UB-Mannheim/tesseract/wiki) and run it as
   administrator. Keep the folder `C:\Program Files\Tesseract-OCR`, the English data (`eng`), and tick "Orientation and
   script detection (osd)".
2. Check: `& "C:\Program Files\Tesseract-OCR\tesseract.exe" --version` (we use v5.5.3) and `--list-langs` (`eng`,
   `osd`).

## 3. Ollama (Reader, path 2: the vision model)

1. Install Ollama for Windows (ollama.com; we use 0.40.6). **Quit the Ollama desktop app** (tray icon → Quit): it holds
   port 11434 and keeps its models outside the project.
2. Start our own Ollama server, with its models in `models\ollama`:
   `powershell -ExecutionPolicy Bypass -File scripts\start_ollama.ps1`
3. Pull the vision model (about 3.2 GB):
   `curl.exe http://127.0.0.1:11434/api/pull -d "{\"model\": \"qwen2.5vl:3b\", \"stream\": false}"`
   The manifest digest must be `fb90415cde1e…` (`models/MANIFEST.md`):
   `curl.exe http://127.0.0.1:11434/api/tags`
4. Without Ollama, the Reader still works: `READER_MODE=late` falls back to OCR with a warning.

## 4. llama.cpp b11139 (Qwen3-4B + Matcher LoRA server)

1. From the llama.cpp GitHub releases, tag **b11139**, download `llama-b11139-bin-win-cuda-12.4-x64.zip` and
   `cudart-llama-bin-win-cuda-12.4-x64.zip`, and check both against the sha256 digests shown on the release page.
2. Unzip both into `tools\llama.cpp\` (`tools\llama.cpp\llama-server.exe` must exist).
3. Newer llama.cpp builds were blocked by Windows Smart App Control on our laptop (T02b); b11139 runs.

## 5. Models (`models\`, pinned by sha256)

```powershell
.venv\Scripts\python scripts\download_models.py          # Qwen3-4B GGUF, NLI Judge, MiniLM embedder; then verifies
.venv\Scripts\python scripts\download_models.py --all    # also the benchmark-only models (e5, bge, rerankers, 0.6B)
.venv\Scripts\python scripts\download_models.py --verify # every file must say OK
```

**Matcher LoRA (`models\hiresignal-lora-f16.gguf`).** It is not on the Hub as GGUF. Convert the team adapter, then
check that its sha256 is `345ed967…` (`models/MANIFEST.md`):
1. download `HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora` at `0b6925b1` and the base model
   `Qwen/Qwen3-4B-Instruct-2507`;
2. run llama.cpp's `convert_lora_to_gguf.py --outtype f16 --base <base dir> <adapter dir>` (llama.cpp source tag
   b5116, as the team did; see `tasks/T02b_report.md`).

This conversion was not re-run in T13: the existing file matches the manifest hash. If a teammate shares the GGUF,
copy it into `models\` and run `--verify`.

**ESCO knowledge base.** `rag/data/esco/` is in the repo. To rebuild it from the pinned public source:
`.venv\Scripts\python rag\build_esco.py`.

## 6. Node 24 + n8n 2.43.7 (portable, inside `tools\`)

```powershell
# Node v24.22.0 portable (nodejs.org/dist/v24.22.0/node-v24.22.0-win-x64.zip, sha256 f9683a19... from SHASUMS256.txt)
Expand-Archive node-v24.22.0-win-x64.zip tools\ ; Rename-Item tools\node-v24.22.0-win-x64 node
New-Item -ItemType Directory tools\n8n | Out-Null
$env:PATH = "$PWD\tools\node;$env:PATH"; Push-Location tools\n8n; npm install n8n@2.43.7; Pop-Location
```

`scripts\start_n8n.ps1` sets everything n8n needs for its own process only:
- data in `.n8n\`;
- listen on 127.0.0.1;
- `N8N_USE_WORKFLOW_PUBLICATION_SERVICE=false` (n8n 2.43 + SQLite workaround);
- file access limited to `data\processed`, `eval\logs` and `eval\outbox`;
- the webhook token from `.env`.

## 7. Configuration

```powershell
Copy-Item config\.env.example .env
```

Edit `.env`:
- `TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe`;
- `WEBHOOK_TOKEN=` a new random secret: `.venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(32))"`;
- leave the other defaults, which are the settings chosen in T09–T13.

`.env` is git-ignored: never commit it.

## 8. Import the n8n workflows (first time)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\n8n_cli.ps1 import:workflow --input=n8n\hiresignal_errors.json
powershell -ExecutionPolicy Bypass -File scripts\n8n_cli.ps1 import:workflow --input=n8n\hiresignal_v1.json
powershell -ExecutionPolicy Bypass -File scripts\n8n_cli.ps1 publish:workflow --id=HsV1Errors000001
powershell -ExecutionPolicy Bypass -File scripts\n8n_cli.ps1 publish:workflow --id=HsV1Main00000001
```

n8n must be stopped while importing. Create the n8n owner account on the first visit to http://localhost:5678.

## 9. Start, check, stop

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_all.ps1   # Ollama -> llama-server -> API -> n8n, with health checks
.venv\Scripts\python -m pytest -q                                # tests (no server needed)
powershell -ExecutionPolicy Bypass -File scripts\stop_all.ps1
```

Health checks:
- `http://127.0.0.1:8090/health` (llama-server);
- `http://127.0.0.1:8010/ready` (API + LLM);
- `http://127.0.0.1:11434/api/version` (Ollama);
- `http://127.0.0.1:5678/healthz` (n8n).

## 10. Run the demo

See `demo/README.md`: three sample inputs (an invite, a reject, a phone photo) sent to the webhook with the token
header, and where the results appear (`eval/outbox/`, the n8n editor, the recruiter form).

**Demo page** (T16): with the stack running, open **http://127.0.0.1:8010/ui/** in a browser (offline, nothing to
install). Upload a CV + job text (+ optional requirement card), press **Run**, and watch each agent. The station API
forwards the run to the n8n webhook and adds the token on the server, so the browser never sees it. **Open a saved
result** shows a `result.json` without running anything (replay, for a slow laptop). See `demo/README.md`.

**Recruiter flow** (T19): **http://127.0.0.1:8010/ui/recruiter.html**, for one job, a confirmed requirement card and
up to 3 candidates, compared requirement by requirement, with human-approved letters. Results stay in `private/batches/`
and approved letters plus the audit log in `eval/outbox/` (both git-ignored). See `docs/RECRUITER_FLOW.md`.

## Not tested from zero in T13

The guide was checked step by step on the development laptop, where the tools were already installed:
- the scripts, `pip check`, `--verify`, start / stop and the demo commands were run;
- the downloads (Python, Tesseract, Ollama, llama.cpp, Node, `npm install`) and the LoRA conversion were **not re-run
  on a clean machine**.

The versions and checksums are the ones recorded in `tasks/T02_report.md`, `tasks/T02b_report.md` and
`models/MANIFEST.md`.
