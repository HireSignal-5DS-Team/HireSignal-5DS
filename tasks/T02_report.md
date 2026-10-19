# T02 report — Environment setup + GPU smoke tests

Date: 2026-10-18. No git commits. One read-only git command was run by mistake; see §3.6.

**Summary:**
- **Done:** Parts A (Python env), B (models), D (n8n) and E (Tesseract steps, which wait for the Approver).
- **Stopped as instructed:** Part C (LoRA check). The installed Ollama refuses LoRA adapters (`Error: LoRA adapters are no longer supported`). The plain model `hs-qwen3-4b` was created and runs 100% on GPU. The fallback choice is in §4.

## 1. Done

- [.gitignore](../.gitignore) now ignores `models/*` (except `models/MANIFEST.md`), `tools/`, `.n8n/` and `*.log`.
- **Part A:**
  - `.venv` created with `py -3.12` (Python 3.12.10).
  - [requirements.txt](../requirements.txt): one frozen file, 75 pinned packages. It uses `--extra-index-url https://download.pytorch.org/whl/cu126` for torch, and pins `pywin32` with a Windows-only marker.
- **Part B:**
  - Four model files copied into `models/`, and the DeBERTa-v3-base judge downloaded.
  - [models/MANIFEST.md](../models/MANIFEST.md) records source, revision, size, SHA-256 and licence for each.
- **Part C** (partial):
  - [config/ollama/Modelfile.hs-qwen3-4b](../config/ollama/Modelfile.hs-qwen3-4b): created as `hs-qwen3-4b`.
  - [config/ollama/Modelfile.hs-matcher](../config/ollama/Modelfile.hs-matcher): written, but `ollama create` refuses it.
  - Not done, because Part C was stopped: `prompts/matcher/v1.md`, `scripts/smoke_matcher.py` and `eval/results/2026-10-18_lora_check/`.
- **Part D:**
  - Portable Node v24.22.0 LTS in `tools/node/`, checked against `SHASUMS256.txt`.
  - n8n 2.43.7 installed locally in `tools/n8n/`.
  - [scripts/start_n8n.ps1](../scripts/start_n8n.ps1) starts it.
  - **n8n is running now** on `http://localhost:5678` (bound to 127.0.0.1, pid 6476), with its data in `.n8n/`. The owner account is not created yet.
- **Part E:** install steps are in §3.4.

## 2. Evidence

### Part A — Python

The CUDA check output:
```
torch 2.14.1+cu126 cuda 12.6 available True
gpu NVIDIA GeForce RTX 4050 Laptop GPU
matmul ok True          # 1024x1024 matmul on cuda
```
- `pip check` gives `No broken requirements found.`
- Clean-install check: `pip install --dry-run --ignore-installed -r requirements.txt` resolves **75/75** packages, with torch `2.14.1+cu126`.
- **Torch wheel choice:** `pip index versions torch` per index:
  - cu126: up to 2.14.1;
  - cu128: up to 2.11.0;
  - cu129: up to 2.9.0;
  - cu130: up to 2.14.1.

  cu126 is the newest torch on a CUDA 12.x index. Driver 581.86 supports CUDA up to 13.0, so 12.6 wheels run on it.
- **The V2 pin conflict is gone.** pip picked `huggingface_hub 1.33.0`, which `sentence-transformers 6.1.0` accepts (`<2.0.0`).

Installed versions of the requested packages:

| package | version | package | version |
|---|---|---|---|
| torch | 2.14.1+cu126 | pymupdf | 1.28.2 |
| torchvision | 0.29.1+cu126 | python-docx | 1.2.0 |
| transformers | 5.20.1 | pillow | 12.3.0 |
| sentence-transformers | 6.1.0 | pytesseract | 0.3.13 |
| huggingface_hub | 1.33.0 | bm25s | 0.3.13 |
| fastapi | 0.143.3 | qdrant-client | 1.19.1 |
| uvicorn | 0.54.0 | networkx | 3.6.1 |
| httpx | 0.28.1 | numpy | 2.5.2 |
| pydantic | 2.14.1 | pandas | 3.0.6 |
| python-multipart | 0.0.32 | python-dotenv | 1.2.4 |
| pytest | 9.1.1 | | |

### Part B — Models

See [models/MANIFEST.md](../models/MANIFEST.md) for the full table.

- **Hashes match the Hub's LFS sha256** for the Qwen3-4B Q4_K_M GGUF, the Qwen3-0.6B Q8_0 GGUF and the xsmall `model.safetensors`, so the copies from the V1 cache are intact. Qwen3-0.6B also matches V2's own pin (`9465e63a…`).
- **The LoRA GGUF is not on the Hub.** The Hub repo `0b6925b1` holds only `adapter_model.safetensors`. V2 converted it locally with llama.cpp `convert_lora_to_gguf.py --outtype f16`, so its hash (`345ed967…`) can only be recorded, not checked against the Hub.
- **DeBERTa-v3-base:**
  - Downloaded at V2's pinned revision `6f5cf0a2…` (MIT licence).
  - `HF_HUB_OFFLINE=1` is set in the user environment. I unset it for that single command only (`env -u HF_HUB_OFFLINE`), not globally.
- **GPU smoke test** of both judges: premise "Built ETL pipelines in Python for five years at a bank.", hypothesis "The candidate has experience with Python.". Labelled **real-GPU**, a single example, not a measurement:
  - xsmall: entailment 0.498 / neutral 0.499 / contradiction 0.003, 258 ms;
  - base: entailment 0.857 / neutral 0.142 / contradiction 0.001, 195 ms.

### Part C — Ollama

Decoding settings in both Modelfiles, with their sources:
- **temperature 0, top_p 1, seed 0** = V2 `matcher/backends_api.py:124-125`.
- **repeat_penalty 1.1:** V2 never set it, so its llama-cpp-python server used the default 1.1 (`llama_cpp/server/types.py:64-65` in the V1 venv, read only). Ollama's default is different, so it is set explicitly.
- **Context size:** `num_ctx` 6144 for the plain model and 4096 for the matcher, as in V2's `llama_v2.json` and `start_v2_windows.ps1`.
- **Template:** ChatML, the template embedded in the GGUF that V2's llama.cpp server used, with the tool-calling branch dropped.
- `max_tokens` (192 for the Matcher, 768 for upstream in V2) is left to each request, because it differs per station.

```
> ollama create hs-qwen3-4b -f Modelfile.hs-qwen3-4b
success
> ollama create hs-matcher -f Modelfile.hs-matcher
Error: LoRA adapters are no longer supported
```
The current Modelfile reference (https://docs.ollama.com/modelfile) lists only `FROM, PARAMETER, TEMPLATE, SYSTEM, LICENSE, MESSAGE, REQUIRES, CAPABILITY`. `ADAPTER` is gone, so this applies to Ollama 0.40.5 as such, not to our file.

`ollama ps` after one generate call on `hs-qwen3-4b`:
```
NAME                  ID              SIZE      PROCESSOR    CONTEXT    RUNNER      UNTIL
hs-qwen3-4b:latest    1047861aec79    3.6 GB    100% GPU     6144       llamacpp    4 minutes from now
nvidia-smi: 3505 MiB / 6141 MiB used
```
That first call took 23.6 s to load the model and 14.9 s to evaluate an 11-token prompt. This is cold-start time, not a latency measurement. `hs-matcher` could not be loaded, so it has no `ollama ps` output.

**LoRA check table:** not run, because Part C was stopped. While preparing it I found a mismatch in V2's reference numbers:
- V2's 0.908 (LoRA) and 0.634 (base) on val (`docs/orchestration/FINAL_REPORT.md:26`) come from runs with different knowledge settings.
- The LoRA run used `knowledge: rag.bm25, k: 3` (`benchmark/results/qwen3-4b-q4+hslora-rag-val/config.json`).
- The 0.634 base run is `qwen3-4b-q4-none-val`, with no knowledge.
- The fair base-with-RAG number is 0.630 (`CONSOLIDATED_val.md`).
- My plan for the check is to run both models without knowledge.

### Part D — n8n

- **Node range:** n8n's docs (https://docs.n8n.io/hosting/installation/npm/) say *"n8n requires a Node.js version between 20.19 and 24.x, inclusive."* The npm registry shows `n8n@2.43.7` with `engines: {"node": ">=24.0.0"}`.
- So I installed Node **v24.22.0** (LTS "Krypton", 2026-10-14): `node-v24.22.0-win-x64.zip: OK` against nodejs.org's `SHASUMS256.txt`. The global Node v25.9.0 is untouched.
- `npm install n8n@2.43.7` was run inside `tools/n8n` with the portable Node, and `n8n --version` gives `2.43.7`.
- **Skipped install scripts:** npm 11.19 skipped install scripts by default (`npm warn install-scripts`), including `sqlite3`, `oracledb` and `kafka`. n8n still started and created `.n8n/database.sqlite`, so its built-in SQLite works without those scripts.
- **Data folder:** n8n writes to `<N8N_USER_FOLDER>\.n8n`, so the script sets `N8N_USER_FOLDER` to the repo root, and the data lands in `YD\.n8n\`. Setting it to `.n8n` itself would have created `.n8n\.n8n`.
- **Start result:**
  ```
  Editor is now accessible via: http://localhost:5678
  GET http://localhost:5678/        -> 200
  GET http://localhost:5678/healthz -> {"status":"ok"}
  Listen: 127.0.0.1:5678 pid 6476
  .n8n/: config, database.sqlite, n8nEventLog.log, nodes, storage
  ```
- The start log is `.n8n_start.log` at the repo root (git-ignored through `*.log`).

## 3. Not done / problems

1. **Part C stopped** (LoRA in Ollama). See §4, question 1.
2. `prompts/matcher/v1.md`, `scripts/smoke_matcher.py` and the `lora_check` results do not exist yet. They depend on the server decision in §4.
3. The VRAM budget is tight. `hs-qwen3-4b` uses 3.6 GB of 6 GB. A second Qwen3-4B with the LoRA, in any server, cannot stay loaded at the same time. Plain and LoRA calls will swap models (V2 swapped too), unless the server can apply the LoRA per request on a single base.
4. **Tesseract** is not installed. Steps for the Approver (admin rights):
   1. Download the official UB Mannheim 64-bit build, the latest listed on https://github.com/UB-Mannheim/tesseract/wiki: `tesseract-ocr-w64-setup-5.5.3.20260724.exe`, from https://github.com/tesseract-ocr/tesseract/releases/download/5.5.3/tesseract-ocr-w64-setup-5.5.3.20260724.exe.
   2. Run it as administrator and keep the **suggested install folder** (`C:\Program Files\Tesseract-OCR`). The wiki warns against installing into an existing folder, because the uninstaller deletes the whole folder.
   3. On the components page, keep **English** language data (`eng`, installed by default). Optionally tick "Orientation and script detection (osd)", which V2's Reader uses for rotation.
   4. Add `C:\Program Files\Tesseract-OCR` to the **user or system PATH**: Settings → System → About → Advanced system settings → Environment Variables → Path → New. This is a global setting, so it is the Approver's choice. Alternatively, leave PATH alone and I will set `TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe` in our `.env`, which needs no global change.
   5. Open a new terminal and tell me. I will then run `tesseract --version` and `tesseract --list-langs`, and expect `eng` (and `osd`) in the list.
5. The n8n owner account is not created; that is the Approver's job, in the browser.
6. **Rule 11 slip:** I ran one read-only git command, `git check-ignore -v models/MANIFEST.md …`, to check the new `.gitignore` rule. It changes nothing, but rule 11 says no git commands at all. I will not repeat it.

## 4. Questions for the Brain

1. **How should we serve the Matcher LoRA?** Options:

   | | (a) llama.cpp fallback, recommended | (b) Merge the LoRA into the base, serve through Ollama |
   |---|---|---|
   | How | llama-cpp-python server on our spare port **8090** with `--lora_path models/hiresignal-lora-f16.gguf`, exactly as V2 ran it | peft merge on the full-precision base (an extra ~8 GB HF download), then llama.cpp `convert_hf_to_gguf`, then quantize to Q4_K_M, then `FROM` in Ollama |
   | Pros | Same weights and runtime as V2's 0.908 measurement | One server |
   | Cons | Adds `llama-cpp-python` with a CUDA wheel to `requirements.txt` (V2 used 0.3.22 cu125; must be resolved on this laptop) | Needs llama.cpp build tools; a second 2.5 GB model file; merge-then-quantize is not the same model as V2's runtime LoRA on Q4, so it must be re-measured |
   | Ollama keeps | Profile, Job Agent, vision Reader, plain Qwen | Everything |

   I recommend (a), and to run the 30-item LoRA check on it.
2. **Downgrade Ollama instead?** I believe older Ollama versions supported `ADAPTER`, but I have not checked which version removed it. Downgrading would mean changing a global install, so I did not look into it. Should I?
3. May I add `llama-cpp-python` to `requirements.txt` if (a) is chosen?
4. **Tesseract:** add it to PATH (a global change), or use `TESSERACT_CMD` in `.env` (local only)?

## 5. Suggested next step

1. The Brain decides question 1.
2. Finish Part C on the chosen server: `prompts/matcher/v1.md`, `scripts/smoke_matcher.py`, and the 30-requirement base vs LoRA check (real-GPU) in `eval/results/2026-10-18_lora_check/`.
3. Meanwhile the Approver:
   - installs Tesseract (§3.4) and confirms, so I can verify `tesseract --version`;
   - creates the n8n owner account at http://localhost:5678.
