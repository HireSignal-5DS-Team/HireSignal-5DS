# T10 — Multimodal Reader: OCR + vision model, late fusion (main) vs early fusion

Read `CLAUDE.md` first. Locked plan (Decision 15): **Path 1 = OCR** (current `services/reader`, PyMuPDF / Tesseract with image clean-up) + **Path 2 = a local vision model via Ollama** (port 11434). **Late fusion is the main method; early fusion is compared.** Budget zero, local only.

## Part 0 — finish T09b Part B (first, ~5 min)
The Approver filled in `rag/eval/queries_review.xlsx`: 22 OK, 10 CHANGE, 0 DROP. Column I already holds the full final label list for each CHANGE row, written by the Brain from the Approver's ticks; his raw ticks are in column J. Run T09b Part B exactly as written in `tasks/T09b_tau_recheck.md`, and append the result to `tasks/T09b_report.md`. If dense MiniLM is no longer best on dev, stop and report before going on.

## Data (already in `data/raw/scans/`, read `PHOTO_MAPPING.csv` + `MANIFEST.csv`)
- 16 phone photos of a screen, plus 5 scan-app PDFs (`L0x_scan.pdf`: image only, no text layer). **File names don't match their sources:** always use `PHOTO_MAPPING.csv`.
- **Ground-truth text** = the text layer of the source digital PDF (`K0x.pdf` / `L0x.pdf`) for the same page(s), read with PyMuPDF.
- **Split (never tune on test):**
  - **dev = all K images** (13 Kaggle photos, no labels). Use them to choose the vision model, prompts and fusion settings.
  - **test = all L images** (L photos + L scans; pairs P02, P15, P43, P47, P52 have gold labels). Report results on these once.

## Part A — vision path
- Pull 2–3 small vision models in Ollama that fit the RTX 4050 (6 GB), for example `qwen2.5vl:3b`, `granite3.2-vision:2b`, `gemma3:4b`. Record name, tag, digest, size and licence in `models/MANIFEST.md`.
- **VRAM:** llama-server (3.25 GB) and the vision model must not need the GPU at the same time. Call Ollama with `keep_alive: 0`, so the vision model unloads after reading (the Reader always runs before the Matcher), or stop llama-server during the benchmark. Report peak VRAM.
- Prompt `reader-vision`:
  - **v0** = naive ("read this CV");
  - **v1** = improved: transcribe exactly, keep reading order and section headings, never add or guess text, mark unreadable parts as `[unclear]`.
  - Store both in `prompts/reader/` and add rows to `prompts/PROMPT_LIBRARY.md`, with before/after numbers measured on dev.
- Pick one model + prompt **on dev**: lowest CER, then lowest hallucination, then speed.

## Part B — the 4 setups (compare all of them)
1. **OCR only:** the current Reader.
2. **Vision only:** Part A's choice.
3. **Late fusion (main):** run both paths separately, then merge in **code**, not in an LLM (rule "LLM judges, code counts"). Suggested merge:
   - align the two texts line by line (difflib);
   - where they agree, keep the line;
   - where they disagree, keep the OCR word if its Tesseract word confidence ≥ a threshold, otherwise the vision word;
   - mark vision-only lines with no OCR support as low-trust (vision models can invent text) and record them as a warning, not as clean text.

   Tune the threshold on dev only. A simpler, well-argued merge is fine, if you explain it.
4. **Early fusion:** one vision-model call with the image plus the OCR text in the prompt: "correct this OCR text using the image; do not add anything that is not in the image". Prompt `reader-early-fusion` v0 → v1, also in the prompt library.

## Part C — measures (per image, per setup; dev and test tables)
- **CER and WER** against the ground-truth text (normalise whitespace and case; say how).
- **Hallucination rate:** share of output words that are not in the ground truth (insertions).
- **Skill terms found:** for the L CVs, how many of the gold requirements' `skill_terms` / key phrases present in the digital text are also present in the setup's text.
- **Latency per page and peak VRAM.**
- Also report a breakdown by condition: close photo / hard photo (L04_p01, L04_p02, L05) / scan.

## Part D — does the decision survive? (test only, L CVs)
For each L image condition, run the setup's text through the real chain: `/profile` → (confirmed requirement card J1–J4) → RAG (V6) → `/match` → `/judge` → `/outcome`. Compare with:
- **(a)** the gold outcome;
- **(b)** the outcome from the original digital PDF;
- **(c)** requirement-level agreement with gold.

Use the 4 setups' outputs (or at least OCR-only, vision-only and the chosen fusion, if time is short). The key line for the report: **"from a phone photo / a scan, the decision matches the digital version in X of Y cases"**. A safe failure counts too: if a bad image leads to **review** instead of a wrong invite or reject, that is the safe outcome, so report it separately.

## Part E — production + n8n
- `/reader` gets a `mode` option (`ocr | vision | late | early`). The default = the setup chosen on dev; fall back to OCR if Ollama is not reachable (with a warning, never a crash).
- Return the per-page route and fusion warnings in the Reader result (low-trust lines, low OCR confidence). If the image is too bad (for example a very high `[unclear]` share or very low OCR confidence), set a review flag, so the outcome becomes **review** and never a silent wrong decision.
- n8n: make sure a photo (JPG/PNG) or a scanned PDF can enter the workflow. Add a Form Trigger with file upload if the webhook doesn't take binary files today. Show the Reader mode in the result.
- Run **one real e2e demo with a phone photo** (e.g. `K01_photo.jpg` = L02 = P15) and save it in `eval/results/<date>_n8n_e2e_photo/`.
- Tests for the new code (merge function, mode switch, Ollama fallback). `pytest -q` must pass.

## Report
- Write `tasks/T10_report.md`: a plain-words summary first, then dev/test tables, the chosen setup and why the others lost, Part D's key line, and problems.
- Add `docs/MULTIMODAL_REPORT.md`, reusable in the final report: method, why late fusion, the tables, examples of one fixed error and one hallucination.
- Stop llama-server, the API and the Ollama model at the end. No git.

**Time:** if time runs short, priority order is: Part 0 → A → B (setups 1–3) → C → D (OCR, vision, late) → E → setup 4. Report clearly what was skipped.
