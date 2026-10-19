# T02 — Environment setup + GPU smoke tests

Read `CLAUDE.md` first (it changed: no git, Ollama is our LLM server, models are copied, tools stay inside this folder).
Answers to your T01 questions: 1) stamp copied code with `a5a03ff`. 2) copy the model files into `models/`. 3) Ollama is the main LLM server (reasons: native n8n Ollama node, JSON-schema structured output, vision models for the Reader, OpenAI-compatible `/v1` for the cloud-backup switch, already running); llama.cpp is only the fallback if the LoRA fails in Ollama. 4) yes, download the better judge. 5) portable Node LTS inside `tools/`, no global change. 6) fresh pins resolved on this laptop.

Add `models/`, `tools/`, `.n8n/` to `.gitignore` (the file only; no git commands).

## Part A — Python environment
1. Create `.venv` with `py -3.12`.
2. Install only what the next tasks need, then freeze the exact versions into `requirements.txt` (one file, installs cleanly):
   torch + torchvision (CUDA 12.x wheel that works with driver 581.86), transformers, sentence-transformers, huggingface_hub (a version compatible with sentence-transformers), fastapi, uvicorn, httpx, pydantic, python-multipart, pytest, pymupdf, python-docx, pillow, pytesseract, bm25s, qdrant-client, networkx, numpy, pandas, python-dotenv.
3. Check: `torch.cuda.is_available()` is True and prints the GPU name. Report the installed versions.

## Part B — Models
1. Copy from the V1 cache (read-only source, list in your T01 report) into `models/`: Qwen3-4B Q4_K_M GGUF, the Matcher LoRA GGUF, Qwen3-0.6B Q8_0 GGUF, DeBERTa NLI xsmall. Record SHA-256 of each file in `models/MANIFEST.md` (name, source repo + revision, size, sha256, licence).
2. Download `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` into `models/` (add it to the manifest).

## Part C — Ollama models + LoRA check
1. Create two Ollama models from OUR files with Modelfiles saved in `config/ollama/`:
   - `hs-qwen3-4b` = `FROM` our Qwen3-4B GGUF (plain; used by Profile, Job Agent).
   - `hs-matcher` = same base + `ADAPTER` our LoRA GGUF.
   Keep the chat template and parameters consistent with how V2 ran Qwen (temperature etc.: read V2 `matcher/` and `config/` for the values and cite them).
2. Show `ollama ps` while each model is loaded (how much is on GPU vs CPU).
3. **LoRA effect check (real-GPU):** copy V2's Matcher prompt p1 (`matcher/prompt.py`) into `prompts/matcher/v1.md` (header per rule 8; mark it "adapted from V2 p1, baseline"). Take 30 requirements from V2's bench-v1 **val** split (`benchmark/data/`), run them through `hs-qwen3-4b` (base) and `hs-matcher` (LoRA) via Ollama's OpenAI-compatible endpoint. Report per model: valid-JSON rate, accuracy vs gold decision, mean latency. Expected: LoRA clearly better (V2 recorded macro-F1 0.908 vs 0.634 on the full val). If the LoRA shows no effect or fails to load, STOP Part C, report, and propose the llama.cpp fallback.
   Script in `scripts/smoke_matcher.py`; results in `eval/results/2026-10-18_lora_check/` (config + per-item outputs + summary).

## Part D — n8n
1. Download a portable Node.js LTS that n8n supports (check n8n's docs for the supported range and cite it) into `tools/node/`. Do not touch the global Node v25.
2. Install n8n with that Node into `tools/n8n/` (local install, not global). Set `N8N_USER_FOLDER` to this repo's `.n8n/` so all n8n data stays here.
3. Write `scripts/start_n8n.ps1` that starts it on port 5678 with those settings. Start it, confirm `http://localhost:5678` answers, then leave it running. (The Approver will create the owner account in the browser.)

## Part E — Tesseract
Tesseract needs an installer with admin rights: do NOT install it yourself. Write the exact install steps (official UB Mannheim Windows build, English language data, PATH) in the report for the Approver, then after he confirms, check `tesseract --version`.

## Part F — Report
`tasks/T02_report.md` (format in CLAUDE.md). Include: installed versions, model manifest, `ollama ps` output, LoRA check table, n8n status, anything that failed.
