# T10b — Late fusion: run OCR and the vision model in parallel (small task)

Read `CLAUDE.md` first. **Start only after T11 is finished and reported.** Approver decision (Yassine, 2026-10-18): keep late fusion (Decision 34) and make it faster by running its two readers at the same time.

## What to change
- In `services/reader/multimodal.py` / `reader.py`, for `mode=late`: run the Tesseract OCR path (CPU) and the Ollama vision call (GPU) **concurrently** for each page, for example with a `ThreadPoolExecutor` (2 workers), then run the same late-fusion merge as today.
- **The output must be byte-identical to the sequential version.** Same text, same low-trust lines, same `review_reasons`, for every image. Only the time changes.
- Add a setting `READER_PARALLEL=1` (default on; `0` = the old sequential path), documented in `config/.env.example`.
- Keep the error behaviour: if Ollama fails or times out, fall back to the OCR result with a warning, as today. An OCR error must not crash the vision path either.
- Multi-page files: pages may stay one after another; parallelism is within each page. Do not run two vision calls at once (6 GB GPU).

## Measure (dev images only; no test re-run needed)
- On the 10 dev photos, measure seconds per page, sequential vs parallel, in two conditions:
  1. **llama-server stopped** (GPU free);
  2. **llama-server running** (as in the full app).
- Check that the outputs are identical for all 10 images (assert in the script).
- Results go in `eval/results/<date>_reader_parallel/`. Update the latency line in `docs/MULTIMODAL_REPORT.md`.

## Tests + report
- Tests:
  - parallel = sequential output (with a fake Ollama client);
  - Ollama-timeout fallback in parallel mode;
  - `READER_PARALLEL=0` path.
- `pytest -q` must pass.
- Write a short `tasks/T10b_report.md`: the time table (2 conditions × 2 modes), the identical-output check, problems. No git. Stop llama-server, the API and Ollama at the end.
