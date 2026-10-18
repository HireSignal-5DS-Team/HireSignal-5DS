# T01 — Repo setup, environment check, reuse inventory

Read `CLAUDE.md` first. This task writes NO pipeline code and installs NOTHING.

## Part A — Repo skeleton
1. `git init` in this folder (branch `main`). Add a `.gitignore` for Python, Node, `.venv/`, `.env`, `private/`, `data/raw/`, model files (`*.gguf`, `*.safetensors`, `*.bin`), `__pycache__/`, `node_modules/`.
2. Create these folders, each with a one-line `README.md` saying what goes there:
   - `n8n/` exported n8n workflows (JSON)
   - `services/` station HTTP endpoints (one module per station: reader, profile, job, matcher, rag, bias, judge, reporter, outcome)
   - `prompts/` versioned prompts + `PROMPT_LIBRARY.md` (empty template with the columns: prompt id, station, version, technique, failure observed, fix, before/after metric)
   - `rag/` knowledge base build + retrieval
   - `data/` (`raw/` git-ignored, `processed/`, `labels/`)
   - `eval/` evaluation scripts + `results/`
   - `docs/` decisions, report material
   - `tests/`, `scripts/`, `config/` (with `.env.example`, placeholders only), `private/` (git-ignored)
3. A short root `README.md`: project one-liner + "work in progress, see CLAUDE.md".
4. First commit.

## Part B — Environment check (report only, change nothing)
Report the exact output/versions of:
- Windows version, CPU, RAM total/free, disk free on C:, `nvidia-smi` (GPU, VRAM, driver, CUDA)
- `node -v`, `npm -v`, and whether `n8n` is installed (`n8n --version` or `npx n8n --version` without installing)
- Python versions available (`py -0` or `python --version`), and whether `C:\Users\semah\HireSignal-Integration\repo\.venv` exists and which Python it uses
- Tesseract installed? (`tesseract --version`)
- Ollama installed? (`ollama --version`, `ollama list`)
- Where the team's model files are on disk (Qwen3-4B GGUF, the Matcher LoRA GGUF, Qwen3-0.6B GGUF, DeBERTa): paths + sizes. Look at V2 docs/scripts (e.g. `docs/integration/V2_WINDOWS_RUN.md`, `scripts/start_v2_windows.ps1`, `RUN_LOCAL.md`) and the Hugging Face cache.
- Which of ports 5678, 8010, 8090 are free; which processes hold 5173, 5174, 8000, 8001, 8081, 8082 (do not stop them)

## Part C — Reuse inventory of team V2 (read-only)
Source: `C:\Users\semah\HireSignal-Integration\v2-agent-integration`. Do not modify it, do not copy code yet.
Write `docs/REUSE_INVENTORY.md` with one section per station of our locked architecture (Reader, Profile/anonymiser, Job Agent, Matcher, RAG, Bias Auditor, Judge, Report Writer, Outcome) plus "data", "evaluation/benchmark", "prompts", "frontend". For each:
- V2 files that implement it (paths)
- Verdict: **reuse as-is** / **adapt** / **rewrite** / **not in V2**, with a one-line reason
- Its tests (paths) and whether they are mock or real
- Dependencies + pinned versions it needs
- Known problems. Check at least these known ones and say where they live: requirements pin conflict (torch 2.14.1 not on cu128 index; `sentence-transformers==6.1.0` vs `huggingface_hub==2.2.0`), Windows path bug in `matcher.factory.judge_config` (`startswith('/')`), validator v2 overfitting val (test macro-F1 0.678 vs raw 0.887), gendered words not anonymised, human-review banner ignoring upstream flags, Qwen HTTP 500 on candidate 2 of a two-CV run.
End with a table: station | verdict | effort (S/M/L) | risk.

## Part D — Report
Write `tasks/T01_report.md` in the format from `CLAUDE.md`, then commit.
