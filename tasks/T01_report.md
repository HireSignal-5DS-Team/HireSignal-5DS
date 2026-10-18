# T01 report — Repo setup, environment check, reuse inventory

Date: 2026-10-18. Nothing was installed and no pipeline code was written. V1 and V2 were only read.

## 1. Done

**Part A: repo skeleton**
- Ran `git init -b main`.
- Wrote [.gitignore](../.gitignore). It covers:
  - Python, Node, `.venv/`;
  - `.env` and `.env.*`, with an exception for `config/.env.example`;
  - `private/`, `data/raw/`;
  - model files: `*.gguf`, `*.safetensors`, `*.bin`, plus `*.pt`, `*.pth`, `*.onnx`;
  - `__pycache__/`, `node_modules/`.
- Created these folders, each with a one-line `README.md`: `n8n/`, `services/`, `prompts/`, `rag/`, `data/` (with `raw/`, `processed/`, `labels/`), `eval/` (with `results/`), `docs/`, `tests/`, `scripts/`, `config/`, `private/`.
  - `.gitkeep` files keep the empty `data/processed` and `data/labels` folders in git.
  - `private/README.md` and `data/raw/` exist locally only, because they are git-ignored.
- [prompts/PROMPT_LIBRARY.md](../prompts/PROMPT_LIBRARY.md): empty template with the required columns.
- [config/.env.example](../config/.env.example): placeholders only. It holds the ports 5678/8010/8090, the local/cloud LLM switch and `MODELS_DIR`.
- Root [README.md](../README.md).
- First commit: `adc8b1e T01: repo skeleton, .gitignore, folder READMEs, env template`.

**Part C:** [docs/REUSE_INVENTORY.md](../docs/REUSE_INVENTORY.md) has one section per station plus data, evaluation, prompts and frontend, the six known problems located, and the summary table.

**Part D:** this report, plus the commit.

## 2. Evidence (Part B — environment, exact output)

| Item | Result |
|---|---|
| Windows | `Microsoft Windows 11 Famille Unilingue 10.0.26200 build 26200` |
| CPU | `13th Gen Intel(R) Core(TM) i7-13650HX`, 14 cores / 20 threads |
| RAM | 31.7 GB total, 14.6 GB free at check time |
| Disk C: | 41.1 GB free of 474.7 GB |
| GPU | `NVIDIA GeForce RTX 4050 Laptop GPU`, 6141 MiB, 0 MiB used, driver **581.86**, `CUDA Version: 13.0` (the highest CUDA the driver supports; no CUDA toolkit was checked) |
| Node / npm | `v25.9.0` / `11.12.1` |
| n8n | **Not installed.** `n8n: command not found`; `npm ls -g n8n` gives `(empty)`; `npx --no-install n8n --version` gives `npx canceled due to missing packages … ["n8n@2.43.7"]`, so the latest on npm is 2.43.7 |
| Python | `py -0p` lists only `-V:3.12 * C:\Users\semah\AppData\Local\Programs\Python\Python312\python.exe`. Bare `python` resolves to the Microsoft Store alias ("Python was not found"), so use `py -3.12` |
| V1 venv | `C:\Users\semah\HireSignal-Integration\repo\.venv` exists. `pyvenv.cfg`: `version = 3.12.10`, home `…\Python312`; `Scripts\python.exe --version` gives `Python 3.12.10` |
| Tesseract | **Not installed**: not on PATH, `where.exe tesseract` finds nothing, no `C:\Program Files\Tesseract-OCR`, nothing under `Program Files (x86)` |
| Ollama | `ollama version is 0.40.5`, listening on `127.0.0.1:11434` (pid 23676). `ollama list`: `llama3.2:1b-instruct-q4_K_M` (807 MB), `qwen3:4b-instruct-2507-q4_K_M` (2.5 GB). Store `~/.ollama/models` is 3.1 GB |

**Ports** (`Get-NetTCPConnection -State Listen`):

| Port | State |
|---|---|
| 5678 (n8n) | free |
| 8010 (station API) | free |
| 8090 (local LLM server) | free |
| 5173, 5174, 8000, 8001, 8081, 8082 (V1/V2) | all free; no process holds them now (V1/V2 not running) |

**Team model files.** All of them are in the **V1 repo's** HF cache, `C:\Users\semah\HireSignal-Integration\repo\.cache\hf\hub\`. This is where `scripts/start_v2_windows.ps1` looks for them (`Find-OneFile` under `<V1>\.cache\hf\hub`). Paths below are relative to that cache:

| Model | Path | Size |
|---|---|---|
| Qwen3-4B Q4_K_M GGUF | `models--unsloth--Qwen3-4B-Instruct-2507-GGUF\snapshots\a06e946b…\Qwen3-4B-Instruct-2507-Q4_K_M.gguf` | 2.4 GB |
| Matcher LoRA GGUF (rev `0b6925b1`) | `models--HireSignal-5DS-Team--hiresignal-qwen3-4b-matcher-lora\snapshots\0b6925b1…\hiresignal-lora-f16.gguf` | 127 MB |
| Qwen3-0.6B Q8_0 GGUF | `models--Qwen--Qwen3-0.6B-GGUF\snapshots\23749fef…\Qwen3-0.6B-Q8_0.gguf` | 610 MB |
| DeBERTa NLI xsmall | `models--cross-encoder--nli-deberta-v3-xsmall` (whole repo) | 552 MB |
| DeBERTa-v3-base-mnli-fever-anli (better judge per V2 docs) | **not on disk** | — |

The user HF cache (`~/.cache/huggingface/hub`, `HF_HOME` unset) has none of the team models. It does have models that may be useful later:
- `intfloat/multilingual-e5-base` (1.1 GB), `all-MiniLM-L6-v2` (88 MB), `all-mpnet-base-v2` (419 MB): embedding candidates for the RAG;
- `oksomu/resume-ner` (250 MB);
- docling layout models (164 MB + 342 MB);
- TinyLlama-1.1B (2.1 GB): a tiny Report Writer candidate;
- Llama-3.2-3B (6.0 GB), Phi-3.5-mini (7.2 GB), Qwen3-4B bnb-4bit (695 MB);
- the dataset `cnamuangtoun/resume-job-description-fit`.

The `*.gguf` search over the whole user folder was stopped after 5 minutes because it was too slow. The two HF caches above were listed directly.

**V2 checks (Part C):**
- Read-only git: `git -C <V2> log -1` gives `a5a03ff`; the branch is `feature/agent-integration`; `git status --short` is clean.
- Re-read by hand to confirm the inventory:
  - `matcher/factory.py:99-111` (`startswith("/")`);
  - `requirements-matcher.txt:8,14` and `rag/requirements.txt:12` (pins);
  - `agents/profile/detect.py:244` (`GENDER_WORDS`);
  - `benchmark/results/final/lora__gated/metrics.md` (macro-F1 0.678 / 0.887).
- The other V2 numbers in the inventory (test counts, metrics) are V2's own recorded results, **not re-run** by us.

**Tests:** none. T01 contains no code.

## 3. Not done / problems

1. **Git identity was missing.** The first commit failed with "Author identity unknown". I set a **repo-local** identity only (`git config user.name "semah"`, `user.email ayachisemah1@gmail.com`) and left the global config unchanged. Tell me if the commits should use another name.
2. **Tesseract is missing.** The Reader's OCR path and its 26 V2 tests cannot run until it is installed. Not installed, because T01 says "install nothing".
3. **n8n is not installed**, and **Node v25.9.0** is the current, non-LTS line. As far as I know, n8n supports only specific LTS Node versions, and the V2 frontend's `engines` also says `>=22.16 <23`. I did not verify this claim against n8n's documentation in T01; check it before installing n8n.
4. Ports 5173–8082 are all free, so V1/V2 are not running now. Rule 7 still applies.
5. The `.venv` (Python 3.12) is not created yet. The only Python on the machine is 3.12.10, so rule 10 can be met.

## 4. Questions for the Brain

1. **Reference commit.** CLAUDE.md rule 6 says to stamp reused code with `feature/agent-integration @ 725923b`. But V2 HEAD is now `a5a03ff`, two commits later:
   - `0593d6a`: retry a transient Qwen 5xx once;
   - `a5a03ff`: Windows startup script.

   Should we copy from `725923b` (read with `git show 725923b:<path>`, which changes nothing) or from HEAD `a5a03ff` and update the stamp? `0593d6a` is the only mitigation for problem (f).
2. **Model files live inside the V1 repo** (`repo\.cache\hf\hub`), and rule 7 says "do not touch the V1 repo". Is **reading** model files from there allowed? Or should we copy or re-download them into our own git-ignored `MODELS_DIR`? The four files take about 3.7 GB and 41 GB is free on C:.
3. **LLM server.** Should it be llama-cpp-python's server on port 8090, as V2 does (LoRA loaded with `--lora_path`)? Or Ollama, which is already installed and running on 11434 and already has `qwen3:4b-instruct-2507-q4_K_M`? Ollama would need a Modelfile `ADAPTER` for the LoRA and would add port 11434 to our list. Note that V2's llama-cpp-python version (0.3.22 cu125) is in no requirements file.
4. **Judge model.** V2's own measurements favour `DeBERTa-v3-base-mnli-fever-anli`: AUROC 0.94 against 0.75 for xsmall on val. It is not on disk. May a later task download it?
5. **Node version for n8n.** Node v25 is installed. Should a later task install a supported LTS Node (for example with nvm-windows), or run n8n through Docker? Docker was not checked in T01; I can check it if useful.
6. **Pin strategy.** V2's four requirements files conflict (torch, huggingface_hub vs sentence-transformers) and leave out llama-cpp-python. Since rule 10 needs one clean dependency set, should the setup task start from fresh pins resolved on this machine (CUDA torch wheel for cu12x), rather than copying V2's pins?

## 5. Suggested next step

T02: environment setup, decided by questions 2, 3, 5 and 6.
- Create `.venv` with Python 3.12.
- Write one `requirements.txt`, resolved and installed on this laptop, with a CUDA torch wheel and llama-cpp-python.
- Install Tesseract and n8n with a supported Node.
- Start the local LLM server on 8090 with Qwen3-4B + LoRA.
- Run a real-GPU smoke test (one Matcher call), and store it in `eval/results/<date>_smoke/`.

After that, T03 could copy the Job Agent (the "reuse as-is" station, effort S) as the first station endpoint on 8010 with its tests.
