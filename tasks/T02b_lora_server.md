# T02b — Serve Qwen3-4B + LoRA with llama.cpp, finish the LoRA check

Read `CLAUDE.md` first. Answers to your T02 questions:

## Decision 1 — LoRA serving: native llama.cpp `llama-server`, ONE base model, LoRA switched per request
- Use the **prebuilt Windows CUDA release of llama.cpp** (official GitHub releases, `llama-server.exe`) unzipped into `tools/llama.cpp/`. Do NOT add `llama-cpp-python` to requirements (no pip CUDA build).
- Start it on port **8090** with our Qwen3-4B Q4_K_M GGUF and our LoRA GGUF loaded but not applied by default (`--lora <file> --lora-init-without-apply`, or the equivalent flags of the version you download; check its `--help` and cite it).
- Per request, choose the adapter scale: `scale 0` = plain Qwen3-4B (Profile, Job Agent), `scale 1` = Matcher. Goal: only ONE copy of Qwen3-4B in the 6 GB VRAM, no model swapping.
- Verify per-request switching really works: same prompt with scale 0 vs scale 1 must give different outputs, and scale 0 must match the plain model's behaviour. If the downloaded version cannot switch per request, fall back to two server aliases (V2's way) and report it.
- Set `n_gpu_layers` to fit fully on the GPU if possible (report VRAM use with `nvidia-smi`), context 4096 like V2. Same sampling settings as V2 (temperature 0, top_p 1, seed 0; cite where V2 set them).
- Write `scripts/start_llm.ps1` (start/stop) and put the URL/model settings in `config/.env.example` + `.env`.
- Ollama stays installed for later models (vision model for the Reader, tiny Report Writer candidates). Unload `hs-qwen3-4b` from Ollama (`ollama stop`) so it does not hold VRAM; keep its Modelfile for the record.

## Decision 2 — Tesseract: local setting, no global PATH change
Use `TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe` in `.env` (and a placeholder in `.env.example`). The Approver will run the installer; after he confirms, run `tesseract --version` and `--list-langs` with that path.

## Part C (redo) — LoRA effect check, fair comparison
You are right that V2's 0.908 vs 0.634 mixed settings. Important: the LoRA was **trained with BM25-ESCO knowledge (k=3) in the prompt**, so running it without knowledge is a train/test mismatch.
1. Copy V2 prompt p1 into `prompts/matcher/v1.md` (header per rule 8: "adapted from V2 p1, baseline").
2. Copy only the knowledge provider V2 used for `rag.bm25, k: 3` (stamp it per rule 6) so both arms get the SAME knowledge block per item.
3. 30 requirements from bench-v1 **val**, fixed list saved with the results. Run 4 arms on the llama-server: base (scale 0) and LoRA (scale 1), each **with** knowledge (main comparison) and **without** knowledge (secondary).
4. Per arm: valid-JSON rate, accuracy and macro-F1 vs gold, false-MET count, mean latency. Results in `eval/results/2026-10-18_lora_check/` (config, item list, per-item outputs, summary table). Script `scripts/smoke_matcher.py`.
5. Label everything real-GPU. 30 items is a smoke test, not a benchmark: say so in the summary.

## Report
`tasks/T02b_report.md` (format in CLAUDE.md).
