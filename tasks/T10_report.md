# T10 report — Multimodal Reader: OCR + vision model, late fusion (main) vs early fusion

## In plain words
- **The Reader can now read phone photos and scans well.** A small local vision model (qwen2.5vl:3b) reads them almost
  perfectly. On the test photos and scans, its character error rate is 2.3%, against 38% for Tesseract OCR alone, and
  it finds all 46 required skill words (OCR alone: 43).
- **Late fusion is the default.** OCR and the vision model both read the page, and plain code merges the two texts.
  Any line that only the vision model saw is kept out of the text and shown as a warning. It is almost as accurate as
  the vision model alone (test 3.6% vs 2.3%) and keeps a check against invented text.
- **Does the decision survive?** From a phone photo or a scan, the decision matches the digital version in 8 of 10
  cases. The other 2 are safe: "review" instead of "reject". There is no wrong invite or reject. With OCR alone there
  was one wrong reject.
- **Fixes found on the way:**
  - a real OCR bug that turned upright photos upside down;
  - a swapped pair of files in the data mapping (L01_scan and L02_scan).
- **Weak point: speed on this 6 GB GPU.** When the whole pipeline runs, the vision model and the main LLM share the
  GPU, and one photo page takes about 2 minutes in n8n (10–15 s when the GPU is free).

## 1. Done
- **Part 0 (T09b Part B):**
  - applied the Approver's review (22 OK / 10 CHANGE / 0 DROP) and re-scored retrieval;
  - bge-small led on dev by 3 of 24 queries, so I stopped and reported;
  - Approver's answer: option (a), keep all-MiniLM-L6-v2 (tie → simpler, faster model). Written in
    `rag/RAG_REPORT.md` §4 and `tasks/T09b_report.md`.
  - Files: `scripts/apply_query_review.py`, `rag/rescore.py`, `rag/eval/queries.jsonl` (+ `queries_drafted.jsonl`),
    `eval/results/2026-10-18_rag_retrieval_checked/`.
- **Part A (vision path):**
  - `scripts/start_ollama.ps1`: our own Ollama server on :11434 with `OLLAMA_MODELS=models/ollama`, set for that
    process only (rule 7b). The user's Ollama desktop app had to be quit, because it held port 11434.
  - Pulled `qwen2.5vl:3b`, `granite3.2-vision:2b`, `gemma3:4b`; recorded in `models/MANIFEST.md` (digest, size,
    licence). The five T09 embedding/reranker models were added there too.
  - Prompts `prompts/reader/vision_v0.md` (naive) and `vision_v1.md` (transcription rules), and
    `prompts/reader/early_fusion_v0.md` / `early_fusion_v1.md`. Four rows added to `prompts/PROMPT_LIBRARY.md` with
    dev before/after numbers.
  - Chosen on dev: **qwen2.5vl:3b + v1**.
- **Part B (4 setups):**
  - `services/reader/multimodal.py`: Ollama call (`keep_alive 0`), the late-fusion merge in code (`late_fuse_vision`
    chosen; `late_fuse` with OCR backbone measured), early fusion, a per-page mode switch, and OCR fallback when
    Ollama is unreachable.
  - `services/reader/reader.py`:
    - word confidences carried through the OCR;
    - `read_cv(..., mode=)`, per-page `page_details`;
    - `quality_reasons()` (low OCR confidence / little text, > 5% `[unclear]`, > 20% low-trust words, vision output
      cut at the token limit);
    - **orientation fix**: an OSD rotation is kept only if OCR is more confident on the rotated image.
- **Part C (measures):** `scripts/eval_multimodal.py`, staged and cached. Measures CER, WER, inserted words,
  `[unclear]` share, skill terms, latency per page and peak VRAM (nvidia-smi polling), plus a breakdown by condition.
  Results and `config.json` are in `eval/results/2026-10-18_multimodal/`.
- **Part D (decision chain):** `scripts/eval_multimodal_chain.py` runs all 4 setups × 10 image cases, plus 5
  digital references, through the station API. Results are in `eval/results/2026-10-18_multimodal/chain/`.
- **Part E (production + n8n):**
  - `/reader` takes a `mode` form field. The default comes from env `READER_MODE`, which is **`late`**.
  - The response adds `mode`, `pages` (route, vision model, latency, `[unclear]` share, fusion counts, number of
    low-trust lines; never CV text) and the Reader's `review_reasons`.
  - **Gate rule 0** (`services/outcome/gate.py`): the Reader's image-quality reasons always mean review, whatever
    `pair_flags` says. None of the 52 gold pairs has one, so the T08/T08b numbers are unchanged.
  - n8n: the webhook already takes JPG/PNG/PDF, so no Form Trigger was needed. The Result node got a `reader` block,
    and the `HTTP /reader` timeout went from 120 s to 900 s. Imported, published, re-exported and cleaned
    (`n8n/hiresignal_v1.json`, 31 nodes); `n8n/README.md` updated.
  - `scripts/n8n_e2e.py` accepts `scan:<file>:<pair>` runs. One real e2e demo with a phone photo is in
    `eval/results/2026-10-18_n8n_e2e_photo/`.
  - `config/.env.example` has the `READER_*` settings.
  - `requirements.txt` adds `RapidFuzz==3.14.6` (MIT; used for CER/WER and the fuzzy support check).
- `tests/test_multimodal.py` (14 tests): merge rules, mode switch, Ollama fallback, `[unclear]` → review, `/reader`
  mode field (no CV text in page summaries), gate rule 0.
- `docs/MULTIMODAL_REPORT.md`: reusable write-up with method, why late fusion, tables, examples and Part D.

## 2. Evidence
**Data and split.**
- dev = 10 photos of the Kaggle source PDFs; test = 6 photos + 5 scans of the 5 labelled L CVs.
- Ground truth = the source PDF's text layer.
- Labels: real-GPU (RTX 4050 6 GB) for the vision models; real-CPU for Tesseract.

**Part A, dev (CER / WER / inserted words / s per page / peak VRAM MiB).**

| model | v0 | v1 |
|---|---|---|
| **qwen2.5vl:3b** | 0.501 / 0.735 / 0.231 / 23.2 / 4,537 | **0.026 / 0.112 / 0.020 / 19.1 / 4,539** |
| gemma3:4b | 0.598 / 0.822 / 0.366 / 19.8 / 4,271 | 0.266 / 0.422 / 0.151 / 16.6 / 3,889 |
| granite3.2-vision:2b | 0.995 / 1.000 / 1.000 / 5.8 / 3,249 | 0.837 / 0.948 / 0.791 / 7.2 / 3,249 |

The qwen dev times include a one-time 72 s CUDA warm-up; on test, qwen averaged 10.7 s per page.

**Part B/C, dev (CER).**

| setup | CER |
|---|---|
| OCR (T09 Reader) | 0.366 |
| OCR (T10, orientation fix) | 0.238 |
| vision | **0.026** |
| late fusion (vision backbone, min_conf 101) | 0.028 |
| early fusion v0 | 0.285 |
| early fusion v1 | 0.191 |

Late-fusion sweep on dev:
- OCR backbone, best 0.096 at min_conf 101 (31 low-trust lines);
- vision backbone, best **0.028** at 101 (1 low-trust line).

**Test, once (CER / WER / inserted words / skill terms / s per page).**

| setup | result |
|---|---|
| OCR | 0.381 / 0.766 / 0.291 / 43/46 / 14.9 |
| vision | 0.023 / 0.049 / 0.036 / 46/46 / 10.7 |
| **late** | **0.036 / 0.063 / 0.037 / 46/46 / 25.6** |
| early | 0.014 / 0.050 / 0.025 / 46/46 / 28.5 |

Peak VRAM 4,513 MiB with llama-server stopped.

Test CER by condition:

| condition | OCR | vision | late | early |
|---|---|---|---|---|
| close photo | 0.014 | 0.001 | 0.001 | 0.004 |
| hard photo | 0.544 | 0.077 | 0.122 | 0.015 |
| scan | 0.503 | 0.003 | 0.006 | 0.018 |

**Part D (test).**

| setup | outcome = digital | safe failure (review) | unsafe | requirements = gold |
|---|---|---|---|---|
| OCR | 7/10 | 2 | **1** (L02 scan: reject, digital review, gold invite) | 52/72 |
| vision | 8/10 | 2 | 0 | 58/72 |
| **late** | **8/10** | **2** | **0** | 59/72 |
| early | 8/10 | 2 | 0 | 57/72 |

The digital PDFs themselves match gold in 2/5 outcomes (28/36 requirements).

**Key line: "from a phone photo or a scan, the decision matches the digital version in 8 of 10 cases (late fusion);
the other 2 are safe failures (review instead of reject); 0 wrong invites or rejects."**

**E2E photo** (`P15` + `K01_photo.jpg`):
- execution 31, HTTP 200, outcome review (same as digital);
- reader block: mode `late`, read_path `["late"]`, 0 low-trust lines;
- identity values found 0, raw CV text in execution no, LoRA scale 1 on all /match calls;
- Reader 119 s (vision 112.8 s), total 172 s, peak VRAM 5,912 MiB.
- The first try (execution 29) failed on the 120 s `HTTP /reader` timeout. The error workflow logged it, and the
  timeout is now 900 s.

**Tests:** `pytest -q` → `412 passed, 1 skipped` (Chroma store test; chromadb uninstalled in T09).

## 3. Not done / problems
- **Split differs from the task text.** The task said "dev = all K images (13)". By `PHOTO_MAPPING.csv`, three
  K-named photos (K01–K03_photo) show L CVs, so they are test. Dev has 10 photos.
- **Data error: `PHOTO_MAPPING.csv` swaps `L01_scan.pdf` and `L02_scan.pdf`.**
  - Measured: L01_scan's vision text matches L02.pdf with CER 0.0004 and L01.pdf with CER 1.25.
  - Corrected in code (`MAPPING_FIX` in `scripts/eval_multimodal.py`); the team's raw file was not edited.
  - Test numbers before the correction were wrong; only the corrected ones are reported.
- **OCR orientation bug (fixed, found on dev).** Tesseract OSD rotated upright, dense photos by 180°. The fix changes
  setup 1, so both versions are reported. The first early-fusion dev run used the old OCR text; it was discarded and
  re-run (`early_on_t09_ocr_discarded/`).
- **Speed with the full stack.** `keep_alive 0` alone does not free the GPU, because llama-server (3.25 GB) stays
  loaded. Ollama still loads qwen2.5vl fully on the GPU and Windows spills into shared memory: ~113 s per page instead
  of 10–15 s. `num_gpu` 0 / 10 / 18 gave 100 / 77 / 72 s. A multi-page photo CV will take several minutes in n8n.
- **Late fusion costs a little accuracy, by design.** Its support check drops vision lines that OCR cannot confirm,
  even when they are right. On the L05 hard photo it dropped 3 correct lines (test hard-photo CER 0.122 vs 0.077 for
  vision alone). Those lines are kept as low-trust warnings in `private/<cv_id>.reader.json`.
- **The low-OCR-confidence rule sends good vision reads to review.** The L01 and L05 scans have OCR confidence below
  60, so they go to review in every mode, even though the vision text is right (late fusion: 8/8 requirements on the
  L01 scan). These are the 2 "safe failures".
- **The vision model silently fixes CV typos** (L04_p01: "destibuted" → "distributed", "Build" → "Built"). The
  Matcher's quotes are checked against the text it is given, so a quote can be "verbatim" from the vision text but not
  from the image.
- **Early fusion** is best on test (0.014) but not chosen. It was the worst vision setup on dev (0.191): it keeps OCR
  omissions, and one page looped to the token cap. The choice is made on dev.
- **The inserted-words metric overstates hallucination.** Most "inserted" words are glued words in the ground truth
  ("Word,Access,PowerPoint"), screen UI text ("Demander à Copilot") or misreads.
- **Tool setup.** The Ollama desktop app was quit to free :11434; it must stay closed while our server runs. The T02
  model `hs-qwen3-4b` stays in the global `~/.ollama` store and was not moved. No global setting was changed.

## 4. Questions for the Brain
1. **Default setup.** I set `READER_MODE=late` because late fusion is the Locked main method and the dev gap to vision
   alone is tiny (CER 0.028 vs 0.026). Vision alone is a bit more accurate (test 0.023 vs 0.036) and twice as fast,
   but has no witness against invented text. Keep `late`?
2. **Low-OCR-confidence rule in vision/late mode.** It caused both safe failures in Part D. Should vision/late mode
   flag review on its own signals instead (`[unclear]` share, low-trust share, truncation), and use OCR confidence
   only in OCR mode? That would be a change chosen on test evidence, so it would need new dev images first.
3. **GPU sharing.** Accept ~2 min per photo page on this laptop, or should a task make the Reader stop/start
   llama-server around the vision call (or run the vision model on a second machine)?
4. **PHOTO_MAPPING.csv:** can the team fix the L01_scan/L02_scan swap in the raw file?
5. **Typo correction by the vision model:** acceptable for the Matcher (it judges skills), or should quotes from a
   vision text be marked "read by a model" in the report?

## 5. Suggested next step
Decide question 2 with a few more dev scans (scan-app PDFs of Kaggle CVs), then move on to the Bias Auditor
(station 5) or the Report Writer (station 7).

---

## Follow-up after the Approver's answers (2026-10-18)

- **Answers:**
  - (1) keep `READER_MODE=late`;
  - (2) keep the low-OCR-confidence rule, as a known limitation;
  - (3) accept the speed;
  - (4) fix the swap in the raw data;
  - (5) accept the typo fixes, as a limitation.
- **Swap fixed in the raw data:**
  - `data/raw/scans/L01_scan.pdf` ↔ `L02_scan.pdf` renamed; L01_scan.pdf now has sha256 `413e3132…` (it was
    L02_scan.pdf);
  - `MAPPING_FIX` removed from `scripts/eval_multimodal.py`;
  - the old cached outputs of the two files were moved to `eval/results/2026-10-18_multimodal/pre_swap_cache/`.
- **Numbers re-checked on the renamed files:**
  - the OCR, vision and early-fusion v1 texts are identical to the old ones;
  - re-running the report gives identical CER/WER/inserted-word/skill-term numbers for dev, test and every condition
    (compared with `summary_before_swap.json`);
  - only the latency of the re-timed pages changed (test per page: vision 10.7 → 11.4 s, OCR 14.9 → 19.4 s,
    late 25.6 → 30.8 s, early 28.5 → 33.2 s; the machine was busier);
  - Part D used the same texts, so its results stand.
- `docs/MULTIMODAL_REPORT.md`: §2 updated, test latencies updated, new §7 "Known limitations" covering the
  low-OCR-confidence rule, typo fixes, speed and the small sample.
