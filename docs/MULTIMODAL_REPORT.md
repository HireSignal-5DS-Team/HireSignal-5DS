# Multimodal Reader — OCR + vision model, late fusion vs early fusion (T10)

Written to be reused in the final report. All numbers are measured; labels say where (real-GPU = RTX 4050 Laptop
6 GB, Ollama 0.40.6; real-CPU = Tesseract 5.5.3). Results: `eval/results/2026-10-18_multimodal/` (`summary.json`,
`rows.csv`, cached outputs per stage), decision chain: `eval/results/2026-10-18_multimodal/chain/`.

## 1. Method

Station 1 (Reader) has two paths for an image page (phone photo, or a scanned PDF page without text layer). PDFs with a
text layer, DOCX and TXT still use the text route (no model).

| path | what | where |
|---|---|---|
| 1 OCR | Pillow clean-up (grey, autocontrast, upscale, orientation) + Tesseract, column detection, median-filter retry on noisy scans | `services/reader/reader.py` |
| 2 vision | a local vision-language model transcribes the page image; prompt `reader-vision` v1 | `services/reader/multimodal.py`, Ollama :11434 |

Four setups were compared:

1. **OCR only**: the Reader as it was (path 1).
2. **Vision only**: path 2.
3. **Late fusion (main, Locked)**: both paths run separately, then **code** merges them (`late_fuse_vision`). No
   LLM decides the merge, following the rule "the LLM judges, code counts".
4. **Early fusion (compared)**: one vision-model call gets the image plus the OCR text and corrects it (prompt
   `reader-early-fusion` v1).

**Late-fusion merge (chosen on dev).**
- The vision text is the backbone, and the OCR words check it. The two word sequences are aligned with difflib
  (normalised words, line ends kept). Then:
  - **agree**: keep the words;
  - **disagree**: keep the OCR word only if its Tesseract confidence ≥ `min_conf`, else keep the vision word;
  - **OCR only**: keep the words if confident, else drop them (moire noise);
  - **vision only**: keep the words if at least half of them occur somewhere in the OCR text, exactly or as a close
    misread (rapidfuzz ratio ≥ 75), i.e. the same text in another reading order. Very short runs (≤ 2 words) are
    also kept. Otherwise the words have **no OCR support**: they are left out of the text and reported as
    **low-trust lines**. Vision models can invent text, and the OCR is the independent witness.
- A first merge with the OCR text as the backbone was also measured (`late_fuse`). It loses whenever the two paths
  disagree on the reading order: the vision lines become "vision only" and are dropped.

**Safety rules.**
- `[unclear]` marks, many low-trust words, a vision output cut at the token limit, or a low OCR confidence each give a
  `reader:*` review reason.
- The outcome gate then always answers **review** (gate rule 0). A bad image must never give a silent invite or reject.
- If Ollama cannot be reached, every mode falls back to OCR with a warning.

**VRAM.**
- llama-server (Qwen3-4B + LoRA) holds 3.25 GB; qwen2.5vl:3b peaks at 4.2–4.5 GB of the 6 GB GPU.
- Ollama is called with `keep_alive: 0`, so the vision model unloads after each page. The Reader always runs before
  the Matcher, so both are never needed at the same time.
- The benchmark ran with llama-server stopped.

## 2. Data and split

- **Pages:** 16 phone photos of a laptop screen and 5 scan-app PDFs (image only), in `data/raw/scans/`.
- **Mapping:** pages are linked to their sources through `PHOTO_MAPPING.csv`, because file names do not match the
  sources. The two scan files `L01_scan.pdf` and `L02_scan.pdf` had swapped names:
  - the scan named L01 matched L02.pdf with CER 0.0004 and L01.pdf with CER 1.25;
  - the files were renamed (Approver, 2026-10-18), so the mapping is now right as written;
  - re-run on the renamed files: the OCR, vision and early-fusion texts are identical, and every CER/WER/skill-term
    number is unchanged.
- **Split by source** (never tune on test):

  | split | pages | sources | use |
  |---|---|---|---|
  | dev | 10 photos | Kaggle source PDFs K01–K05, no labels | choose model, prompts, merge, threshold |
  | test | 6 photos + 5 scans | labelled CVs L01–L05: pairs P02, P15, P47, P52, P43 | reported once |

  The task text said "dev = all K images (13)". Three K-named photos are photos of L PDFs, so they are test.
- **Ground truth:** the text layer of the source PDF page(s), read with PyMuPDF through the Reader's own text route.
  The Kaggle text layers contain mojibake (`â€"`, `Â`), which adds the same small error to every setup.
- **Normalisation before scoring:** NFKC, lower case, Markdown marks (`* # \``) and `[unclear]` removed, whitespace
  collapsed.
- **Metrics:**
  - CER: Levenshtein distance over characters ÷ ground-truth length;
  - WER: the same over words;
  - **inserted words** (hallucination proxy): output words not in the ground truth (multiset difference) ÷ output
    words;
  - **skill terms** (test): the gold requirements' `skill_terms` that are written in the digital text and also found
    in the setup's text.

## 3. Vision model and prompt (dev, real-GPU, same settings for all: temperature 0, num_ctx 8192, max 2048 tokens, image ≤ 1536 px)

| model (Ollama, Q4_K_M) | prompt | CER | WER | inserted words | s/page | peak VRAM MiB |
|---|---|---|---|---|---|---|
| qwen2.5vl:3b | v0 "Read this CV." | 0.501 | 0.735 | 0.231 | 23.2* | 4,537 |
| **qwen2.5vl:3b** | **v1 (transcription rules)** | **0.026** | **0.112** | **0.020** | 19.1* | 4,539 |
| gemma3:4b | v0 | 0.598 | 0.822 | 0.366 | 19.8 | 4,271 |
| gemma3:4b | v1 | 0.266 | 0.422 | 0.151 | 16.6 | 3,889 |
| granite3.2-vision:2b | v0 | 0.995 | 1.000 | 1.000 | 5.8 | 3,249 |
| granite3.2-vision:2b | v1 | 0.837 | 0.948 | 0.791 | 7.2 | 3,249 |

\* The qwen dev times include a one-time 72 s CUDA warm-up on the first page. On test, qwen2.5vl:3b v1 averaged
11.4 s per page.

**Choice: qwen2.5vl:3b + v1** (lowest CER, then lowest inserted words).
- v0 → v1 is the prompt's main before/after: with v0 the model summarised ("Certainly! Here is a summary of the key
  points from the CV:", Markdown headings, shortened bullets).
- granite answered "unanswerable" or looped.
- gemma skipped and reworded lines. On dev K06 it gave 404 of 571 words, and "regulatory/corporate compliance,
  strategic planning" became "regulatory and corporate compliance, planning".

## 4. The four setups

### Dev (10 photos)

| setup | CER | WER | inserted words | s/page |
|---|---|---|---|---|
| 1 OCR only (T09 Reader) | 0.366 | 0.518 | – | 10.4 |
| 1 OCR only (T10 Reader, orientation fix) | 0.238 | 0.395 | 0.240 | 4.8 |
| 2 vision only | **0.026** | 0.112 | 0.020 | 19.1 |
| 3 late fusion (vision backbone, min_conf 101) | 0.028 | 0.114 | 0.020 | 23.9 |
| 4 early fusion v0 | 0.285 | 0.448 | 0.124 | 20.4 |
| 4 early fusion v1 | 0.191 | 0.319 | 0.110 | 20.2 |

**Late-fusion sweep on dev (CER).**

| min_conf | 0 | 40 | 60 | 80 | 90 | 101 |
|---|---|---|---|---|---|---|
| OCR backbone | 0.242 | 0.149 | 0.128 | 0.113 | 0.099 | 0.096 |
| **vision backbone** | 0.188 | 0.105 | 0.081 | 0.064 | 0.033 | **0.028** |

Low-trust lines on dev: 31 with the OCR backbone, 1 with the vision backbone. 101 means an OCR word never replaces
the vision word. On phone photos Tesseract was often confidently wrong (dev K04_p01: "Expenence" for Experience at
confidence 91, "focal" for local at 87), so its word confidence did not help. In this merge the OCR's role is the **support check** (low-trust lines) and the
fallback.

### Test, reported once (6 photos + 5 scans of the 5 labelled CVs)

Latency is per page and includes the two scans re-run after the file rename. That re-run happened on a busier machine,
so the times are a little higher than in the first run (vision 10.7 → 11.4 s); the quality numbers did not change.

| setup | CER | WER | inserted words | skill terms found | s/page | peak VRAM MiB |
|---|---|---|---|---|---|---|
| 1 OCR only | 0.381 | 0.766 | 0.291 | 43/46 | 19.4 | – |
| 2 vision only | 0.023 | 0.049 | 0.036 | **46/46** | 11.4 | 4,513 |
| 3 late fusion | 0.036 | 0.063 | 0.037 | **46/46** | 30.8 | 4,513 |
| 4 early fusion v1 | **0.014** | 0.050 | 0.025 | **46/46** | 33.2 | 4,513 |

By condition (test, CER):

| condition | pages | OCR | vision | late | early |
|---|---|---|---|---|---|
| close photo | 3 | 0.014 | 0.001 | 0.001 | 0.004 |
| hard photo (L04_p01, L04_p02, L05) | 3 | 0.544 | 0.077 | 0.122 | **0.015** |
| scan | 5 | 0.503 | **0.003** | 0.006 | 0.018 |

Readings:
- **Vision wins on bad images.** On close photos OCR is already good (CER 0.014). On hard photos and scans it fails
  (0.50–0.54), while every vision setup stays below 0.13.
- **Late fusion costs a little accuracy.** On hard photos it is behind vision alone (0.122 vs 0.077): the support
  check dropped 3 correct lines of L05_photo as low-trust, because the OCR could not read them. That is the price of
  never using an unwitnessed vision line as clean text. The lines are not lost: they are listed as warnings.
- **Early fusion is best on test but the worst vision setup on dev** (0.191 on dev). Given the OCR text, the model
  keeps the OCR's structure and omissions: on dev K06 the OCR missed the summary paragraph, and the early-fusion text
  misses it too, while vision alone has it. On one dev page (K08_p01) it looped on a sentence until the token cap
  (CER 1.30). The choice is made on dev, so test cannot change it.
- **Inserted words overstate hallucination.** Most "inserted" words are real:
  - the screen's PDF-viewer text ("Demander à Copilot", "2 sur 2");
  - words the ground truth glues together ("Word,Access,PowerPoint,Excel");
  - misreads ("aichttp" for aiohttp, "Rediis").

  No invented sentence was found in the vision v1 outputs on test. But the model **silently corrects the CV**: on
  L04_p01 it wrote "distributed CRM", "business intelligence" and "Built ..." where the CV says "destibuted CRM",
  "business intellegence" and "Build ...". That is harmless for the skills, but the text is not an exact copy.

### 4b. Late fusion, sequential vs parallel (T10b, dev photos, real-GPU + real-CPU)

Since T10b, `READER_PARALLEL=1` (the default) runs Tesseract (CPU) and the vision call (GPU) for a page **at the same
time**, then the same merge. Pages still go one after another, with one vision call at a time.
- **Output:** byte-identical to the sequential path (text, routes, warnings, review reasons, page details): 10/10 and
  3/3 asserted.
- **Data:** `eval/results/2026-10-18_reader_parallel/` (`scripts/eval_reader_parallel.py`).

| condition | pages | sequential s/page (mean / median) | parallel s/page (mean / median) | speed-up |
|---|---|---|---|---|
| llama-server stopped (GPU free) | 10 | 25.4 / 26.8 | **15.7 / 16.6** | ×1.62 |
| llama-server running | 10 | 24.9 / 23.5 | **17.7 / 18.6** | ×1.40 |
| full stack (llama-server + API, Judge + embedder loaded) | 3 | 26.4 / 27.4 | **21.5 / 19.8** | ×1.23 |

The gain is the OCR time hidden behind the vision call. It is smaller when the other services are loaded (×1.40,
×1.23); the reason was not isolated.

## 5. Examples

**One fixed error.**
- **OCR orientation (dev K05_p01).** Tesseract OSD said "rotate 180" (confidence 2.1) for an upright photo of a dense
  page, so the Reader read it upside down: "WADVNVWIW LoafOud ALVYORNOD" = CORPORATE PROJECT MANAGER, CER 0.78.
  - Fix in path 1: keep the OSD rotation only if OCR is more confident on the rotated image.
  - Result: CER 0.78 → 0.22 (K08_p02: 0.81 → 0.09), dev OCR CER 0.366 → 0.238.
  - The hard test photo L04_p01 had the same problem (0.81 → 0.55).
- **Misread words fixed by the vision path (dev K04_p01).**
  - OCR: "© Mamged project schedule and focal and remote stffto collect Water Main data , and update \ and GIS Water
    system Main data collection Sil project. p"
  - Vision and late fusion: "Managed project schedule and local and remote staff to collect Water Main data and
    update GIS system."

**One hallucination.**
- Early fusion v1 on dev K08_p01 repeated "*Superior knowledge of INFOSEC/NETOPS and highly-motivated mentor with
  proven dedication to self and subordinate improvement." until the 2,048-token cap (`done_reason: length`, 10,419
  characters for a 5,494-character page).
- Production catches this case: `reader:vision_output_truncated` sends the pair to review.
- Milder kinds of invented text:
  - vision prompt v0 summarised the CV instead of transcribing it;
  - vision v1 silently fixed the CV's spelling ("destibuted" → "distributed", test L04_p01). This also matters for the
    Matcher: its quotes must be exact substrings of the CV text it is given, which here is the vision text.

## 6. Does the decision survive? (test only, real chain, real-GPU)

**Method.**
- For each labelled CV and image condition, each setup's text went through the real station API: `/reader` (text
  upload) → `/profile` → confirmed requirement card → `/rag/search` (V6) → `/match` → `/judge` → `/outcome` (T08b
  gate).
- The Reader's image-quality review reasons were added as pair flags, exactly as `read_cv` would give them.
- Script: `scripts/eval_multimodal_chain.py`; results: `eval/results/2026-10-18_multimodal/chain/`.

**Results.** Each cell gives the outcome and, in brackets, the requirements that agree with gold. `*` = a `reader:*`
review reason, which sends the pair to review (gate rule 0).

| CV (pair) | condition | gold | digital PDF | OCR | vision | late | early |
|---|---|---|---|---|---|---|---|
| L01 (P02) | close photo | reject | reject (7/8) | reject (7/8) | reject (7/8) | reject (7/8) | reject (7/8) |
| L01 (P02) | scan | reject | reject (7/8) | review* (6/8) | review* (7/8) | review* (8/8) | review* (7/8) |
| L02 (P15) | close photo | invite | review (3/6) | review (3/6) | review (3/6) | review (3/6) | review (3/6) |
| L02 (P15) | scan | invite | review (3/6) | **reject (1/6)** | review (3/6) | review (3/6) | review (3/6) |
| L03 (P47) | close photo | review | review (7/8) | review (7/8) | review (7/8) | review (7/8) | review (7/8) |
| L03 (P47) | scan | review | review (7/8) | review (7/8) | review (7/8) | review (7/8) | review (6/8) |
| L04 (P52) | hard photo | invite | review (6/6) | review (4/6) | review (6/6) | review (6/6) | review (6/6) |
| L04 (P52) | scan | invite | review (6/6) | review* (6/6) | review* (6/6) | review* (6/6) | review* (6/6) |
| L05 (P43) | hard photo | review | reject (5/8) | reject (6/8) | reject (6/8) | reject (6/8) | reject (6/8) |
| L05 (P43) | scan | review | reject (5/8) | review* (5/8) | review* (6/8) | review* (6/8) | review* (6/8) |

| setup | outcome = digital | safe failure (review instead) | unsafe change | requirements = digital | requirements = gold |
|---|---|---|---|---|---|
| 1 OCR only | 7/10 | 2 | **1** (L02 scan: reject, digital review, gold invite) | 61/72 | 52/72 |
| 2 vision only | 8/10 | 2 | 0 | 70/72 | 58/72 |
| **3 late fusion (default)** | **8/10** | **2** | **0** | 69/72 | 59/72 |
| 4 early fusion | 8/10 | 2 | 0 | 69/72 | 57/72 |

**Key line: from a phone photo or a scan, the decision with late fusion matches the digital version in 8 of 10
cases. The other 2 are safe failures (review instead of reject), and none is a wrong invite or reject.** With OCR
alone: 7 of 10, plus one wrong reject.

Readings:
- **The two safe failures are the low-OCR-confidence rule at work.**
  - The L01 and L05 scans have OCR confidence below 60, so `reader:low_confidence_or_little_text` sends them to review
    even when the vision text is right. On the L01 scan, late fusion even has 8/8 requirements right.
  - This is the price of "a bad image never gives a silent decision".
  - L04 scan has the flag too, but its digital outcome is already review.
- **The one unsafe change is OCR only.** On the L02 scan (file `L01_scan.pdf`), Tesseract misread many words while
  reporting a mean confidence of 81.4, which is above the review threshold: "bichucing" for including, "Eirveylissty
  Levee: Mapper" for "years: 2 / English level: upper". No flag was raised, the Matcher found 1/6 requirements, and the gate
  rejected a gold "invite" candidate (the digital version gives review). Vision and both fusions read the page right.
- **The Reader is no longer the weak link for these CVs.** The digital PDF itself agrees with gold on only 2/5
  outcomes (28/36 requirements). Those errors come from the Matcher, the Judge and the gate (see T06–T08), not from
  reading.

## 7. Known limitations (accepted by the Approver, 2026-10-18)

- **The low-OCR-confidence rule also applies in vision and late mode.**
  - A page with mean Tesseract confidence below 60 always gives `reader:low_confidence_or_little_text`, so the pair
    goes to review, even when the vision text is right.
  - This caused both safe failures in Part D (the L01 and L05 scans; late fusion had 8/8 requirements right on the
    L01 scan).
  - Kept on purpose: a bad image must never lead to a silent decision.
- **The vision model silently fixes typos in the CV** ("destibuted" → "distributed", "Build" → "Built", test
  L04_p01).
  - The Matcher's verbatim quotes are checked against the text it is given, i.e. the vision text, not the image.
  - Harmless for skill decisions, but the text is not an exact copy of the page.
- **Speed on a 6 GB GPU.** In the first T10 e2e, one photo page took about 2 minutes in `HTTP /reader` (vision call
  113 s) while llama-server and the API were loaded. T10b could not reproduce this: with llama-server alone, and with
  the full stack (llama-server + API with the Judge and the RAG embedder on the GPU), a late-fusion page took
  25–26 s sequential and 18–22 s parallel (section 4b). The cause of the 2-minute case was not found (possibly a
  different GPU memory state at that time); the n8n timeout stays at 900 s.
  - In the T13 final evaluation through n8n (full chain, shared GPU), the Reader took a mean of 128 s per photo / scan
    CV (max 182 s; `docs/FINAL_EVAL.md` §2). So the slow case does appear in the full chain.
- **Small sample.** Results come from 10 dev pages and 11 test pages (5 labelled CVs). Use them as indications, not
  final rates.
