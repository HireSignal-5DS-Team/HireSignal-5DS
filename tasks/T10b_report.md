# T10b report — Late fusion: OCR and the vision model in parallel

**In plain words:** in late-fusion mode, the Reader now runs Tesseract and the vision model for a page at the same
time instead of one after the other. The text it produces is exactly the same, and a photo page is read about 1.2–1.6×
faster (from ~25 s to ~16–22 s).

## 1. Done
- `services/reader/reader.py`:
  - `_late_page_parallel`: a `ThreadPoolExecutor` with 2 workers runs the OCR path (`_ocr_with_cleanup`) and the
    vision call at the same time, then the same `read_image_page` merge runs;
  - the image is loaded once before the threads start, because PIL loads lazily;
  - OCR warnings are added first, as in the sequential path, so the warning order is the same;
  - `READER_PARALLEL=1` (default) uses it; `0` = the old sequential path. Only `mode=late` is parallel; pages stay one
    after another, with one vision call at a time.
- `services/reader/multimodal.py`:
  - `vision_or_error` returns the vision result, or the `VisionUnavailable` error as a value;
  - `read_image_page(..., vision=)` takes a pre-computed result. The fallback behaviour is unchanged: a vision
    error or timeout gives "OCR only + warning".
- **OCR error in parallel mode:** the vision call is allowed to finish and its thread ends cleanly, then the same
  `ReaderError` is raised as in the sequential path. Nothing crashes inside the vision thread, and the behaviour
  matches `READER_PARALLEL=0`.
- `config/.env.example`: `READER_PARALLEL=1`, documented.
- `scripts/eval_reader_parallel.py`: dev photos; sequential vs parallel alternated per image; a warm-up call first; an
  assert that the outputs are identical.
- `tests/test_reader_parallel.py` (5 tests):
  - parallel = sequential, with a fake Ollama client;
  - Ollama timeout → OCR fallback in parallel mode, the same as sequential;
  - `READER_PARALLEL=0` uses the sequential path;
  - an OCR error is raised only after the vision call has finished;
  - the two readers really overlap.
- `docs/MULTIMODAL_REPORT.md`: new §4b (time table) and an updated speed limitation in §7.

## 2. Evidence (dev photos, real-GPU RTX 4050 + real-CPU Tesseract; `eval/results/2026-10-18_reader_parallel/`)

| condition | pages | sequential s/page (mean / median) | parallel s/page (mean / median) | speed-up | identical outputs |
|---|---|---|---|---|---|
| 1. llama-server stopped | 10 | 25.4 / 26.8 | **15.7 / 16.6** | ×1.62 | 10/10 |
| 2. llama-server running | 10 | 24.9 / 23.5 | **17.7 / 18.6** | ×1.40 | 10/10 |
| extra: full stack (llama-server + API with Judge + RAG embedder on GPU) | 3 | 26.4 / 27.4 | **21.5 / 19.8** | ×1.23 | 3/3 |

- The identical-output check is an assert in the script, covering text, routes, warnings, review reasons and page
  details (all except the measured vision latency). Every page passed.
- `pytest -q` → `437 passed, 1 skipped` (the Chroma store test).

## 3. Not done / problems
- **The 2-minute page from the T10 e2e did not reproduce.** In T10, a photo page took ~113 s for the vision call while
  llama-server and the API were loaded. That is why I added the "full stack" condition beyond the two the task asked
  for. Even there, a page takes ~26 s sequential and ~21 s parallel. The cause of the T10 slowness was not found
  (possibly a different GPU memory state at that time). The n8n `HTTP /reader` timeout stays at 900 s to be safe.
- The full-stack condition used only 3 photos, since the expected slowness did not happen.
- Early fusion is not parallel: its vision prompt needs the OCR text first.

## 4. Questions for the Brain
- None.

## 5. Suggested next step
Continue with the next station (Report Writer).
