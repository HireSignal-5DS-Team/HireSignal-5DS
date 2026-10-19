# T03 report — structured output, full val, real data, labelling kit

Date: 2026-10-18. No git commands were run. Every model result here is **real-GPU** (RTX 4050 Laptop 6 GB, llama.cpp b11139-42916d83f), on the **synthetic** bench-v1. The test split was not touched.

**Summary:**
- JSON-schema constrained decoding takes the base model's valid-JSON rate from 0.900 to **1.000** and leaves the LoRA's output byte-identical (30/30 items).
- Full val, 202 requirements, with the schema: macro-F1 **LoRA 0.892 vs base 0.703**.
- All three real datasets are downloaded and documented.
- The 40-pair blind labelling kit is ready for the labelers.

## 1. Done

**Part A: constrained decoding + full val**
- [services/matcher/schema.json](../services/matcher/schema.json): adapted from V2 `matcher/json_schemas/ModelAnswer.schema.json` and `matcher/schemas.py` `ModelAnswer`.
  - Same enums, same `maxItems 3` and `maxLength 600`, same title, and `additionalProperties: false`.
  - One change: `evidence` is **required** (V2 defaults it to `[]`). Prompt matcher-v1 asks for 4 keys and our strict parser checks for 4. Every object valid under our schema is also valid under V2's.
- [scripts/smoke_matcher.py](../scripts/smoke_matcher.py):
  - `--schema FILE` sends `response_format: {"type": "json_object", "schema": …}`.
  - `--n 0` runs all val requirements.
  - Per-class F1 and a confusion matrix are added to `summary.json` / `summary.md`.
- [scripts/diff_arms.py](../scripts/diff_arms.py): item-by-item diff of two runs.
- [eval/results/2026-10-18_schema_check/](../eval/results/2026-10-18_schema_check/): the same 30 items as T02b, base_k and lora_k, with the schema. Includes `diff_vs_lora_check.txt` and `NOTES.md`.
- [eval/results/2026-10-18_val_full/](../eval/results/2026-10-18_val_full/): all 202 val requirements, base_k and lora_k, with schema and BM25-ESCO k=3. Includes `config.json`, per-item `.jsonl` files, `summary.*`, `run.log` and `NOTES.md`; NOTES and the summary say the data is synthetic.
- [prompts/PROMPT_LIBRARY.md](../prompts/PROMPT_LIBRARY.md): new row `guard-matcher-json-schema`, a serving-level guardrail with before/after numbers.
  - `prompts/matcher/v1.md` is not edited (rule 8). The prompt text did not change.
- llama-server stopped at the end (`start_llm.ps1 -Stop`).

**Part B: real data** (all in `data/raw/`, git-ignored)
- Djinni CVs + jobs (parquet, at pinned HF revisions):
  - [scripts/djinni_stats.py](../scripts/djinni_stats.py) writes `data/stats/djinni_stats.json` (counts only).
  - Its phone rule has a built-in assert self-check.
- Kaggle Resume Dataset: downloaded with the Kaggle API (`~/.kaggle/kaggle.json` exists); PDF counts in `data/stats/kaggle_pdf_counts.txt`.
- Vanetik: all 5 vacancies are software-developer jobs, so I downloaded it as a GitHub zip (no `git clone`, rule 11), commit `7ee8f043`.
- [data/DATA_CARD.md](../data/DATA_CARD.md): link, licence, size, format, use and limits for each source.

**Part C: labelling kit** (built by [scripts/build_labelling_kit.py](../scripts/build_labelling_kit.py), seed 20261018, no model used)
- `data/processed/jobs/J1..J4.txt`:

  | job | role | Djinni id |
  |---|---|---|
  | J1 | Data Scientist | `617ef5c1…` |
  | J2 | Data Engineer | `1d864d06…` |
  | J3 | ML Engineer | `f87c22c3…` |
  | J4 | Python BackEnd Developer | `0dc63314…` |

  - I chose these by reading the candidates for a clear Requirements list.
- `data/processed/cvs/<djinni_id>.txt`: 40 CVs.
  - Each file has a header (Position, Experience years, English level) and then the Djinni `CV` column.
  - CVs with any personal-data regex hit, or outside 400-3000 characters, were skipped.
- [data/labels/pairs.csv](../data/labels/pairs.csv): 40 pairs with keyword, experience and selection stratum.
  - Strata per job: strong 3, partial 4, weak 3, giving 12 / 16 / 12 in total.
  - **strong**: main keyword and experience ≥ the job's Djinni "Exp Years".
  - **partial**: main keyword and experience between 1 year and the job's years.
  - **weak**: 2 CVs with the main keyword and ≤ 0.5 years, plus 1 CV with an adjacent keyword.
  - Main / adjacent keywords: J1 Data Science / Data Analyst, J2 Data Engineer / SQL, J3 Data Science / Python, J4 Python / Data Engineer.
- [data/labels/requirements_draft.csv](../data/labels/requirements_draft.csv): 28 DRAFT requirements (J1 8, J2 6, J3 8, J4 6).
  - Each has kind, category, min_years and the exact source sentence. The build script asserts that every sentence is a verbatim substring of the job text.
- `data/labels/labelling_sheet.xlsx`, three sheets:
  - `requirements`: 280 rows (pair × requirement), with A/B decision dropdowns (MET/MISSING/UNCERTAIN) and quote columns;
  - `pairs`: 40 rows, with A/B outcome dropdowns (invite/review/reject) and a reason;
  - `job_requirements`: the draft for step 0.
  - It contains no model predictions and no stratum, and pairs are shuffled within each job.
- [data/labels/LABELLING_GUIDE.md](../data/labels/LABELLING_GUIDE.md): one page with definitions, outcome rules, examples and time (about 3-4 h per labeler).
- [requirements.txt](../requirements.txt): added openpyxl, pyarrow, kaggle and their dependencies (pinned). `pip check`: no broken requirements.

## 2. Evidence

**llama-server API for the schema:** b11139 `tools/server/README.md` (fetched at tag b11139), line 1316:
> "The `response_format` parameter supports both plain JSON output (e.g. `{"type": "json_object"}`) and schema-constrained JSON (e.g. `{"type": "json_object", "schema": {…}}` …)"

- Also line 571 (the `json_schema` field of `/completion`) and `--help` lines 295-301 (`--grammar`, `-j, --json-schema`, server-wide).
- I used the per-request `response_format` form, which is also the form V2 used (`matcher/backends_api.py:127`).
- **Grammar check:** the prompt "Write one short sentence about cats. No JSON." gives plain text without the schema. With the schema it gives `{"decision": "MISSING", "basis": "not_documented", "evidence": [], …}`.

**30 items, before (T02b, no schema) vs after (schema), BM25-ESCO k=3:**

| arm | valid JSON | accuracy | macro-F1 | false-MET | raw output identical |
|---|---|---|---|---|---|
| base_k | 0.900 → **1.000** | 0.633 → 0.733 | 0.647 → 0.728 | 0 → 0 | 27/30 |
| lora_k | 1.000 → 1.000 | 0.933 → 0.933 | 0.911 → 0.911 | 0 → 0 | **30/30** |

- `diff_vs_lora_check.txt`: the 3 base items that changed (val-027 r1, val-033 r3, val-034 r3) are exactly the 3 invalid template-copy replies. All 3 now give `MET`, which equals gold.
- **LoRA results are unchanged item by item.**
- Mean latency is about 0.35-0.4 s higher per call with the schema (base 1.42 → 1.81 s, LoRA 1.15 → 1.47 s). This is probably grammar overhead, but I have not profiled it.

**Full val** (202 requirements; gold MET 86, MISSING 77, UNCERTAIN 39), with the schema:

| arm | valid JSON | accuracy | macro-F1 | F1 MET / MISSING / UNCERTAIN | false-MET | verbatim quotes | latency |
|---|---|---|---|---|---|---|---|
| base_k | 1.000 | 0.718 | 0.703 | 0.861 / 0.683 / 0.567 | 4 | 153/153 | 1.72 s |
| **lora_k** | 1.000 | **0.916** | **0.892** | 0.955 / 0.920 / 0.800 | 6 | 148/148 | 1.33 s |

Confusion matrices (rows = gold; columns = predicted MET / MISSING / UNCERTAIN):
- base: MET 68/3/15, MISSING 2/43/32, UNCERTAIN 2/3/34. It over-predicts UNCERTAIN (81 predicted vs 39 gold).
- LoRA: MET 84/2/0, MISSING 2/75/0, UNCERTAIN 4/9/26. It **under-predicts UNCERTAIN** (26 vs 39). 13 of 39 gold-UNCERTAIN items become MET (4) or MISSING (9).

Other checks:
- **Determinism:** the 30 schema-check items have identical raw output inside the full run (30/30 for both arms).
- **False-MET for LoRA:** val-006 r1, val-009 r3, val-016 r1, val-017 r1, val-028 r4, val-029 r4. These are the harmful errors; the coming validator and Judge must catch them.
- **Run time:** about 10 min wall-clock for both arms (config 07:11:50 → summary 07:22:06). Model time: base 5.8 min, LoRA 4.5 min.

**Data:**
- Djinni: CVs 210,250 × 11 and jobs 141,897 × 10, all `CV_lang = en`. Licence `mit` on both dataset cards.
  - CV median length 751 characters (mean 944).
  - Personal-data regex: email 0, phone 123, profile/messenger words 5,242, name phrases 3,222; any hit 8,499 (4.0 %).
  - The first phone regex counted year ranges ("2019 - 2021"). I fixed it with a ≥ 10-digit / not-a-year-range rule plus asserts.
- Kaggle: 2,484 PDFs (= the 2,484 rows of `Resume.csv`); **INFORMATION-TECHNOLOGY has 120**. Licence `CC0-1.0` in the Kaggle metadata.
  - The IT texts are mostly support/management: 112/120 contain "support"/"help desk", 1 contains "data scien", 0 contain "machine learning".
- Vanetik: GPL-3.0; 5 software-developer vacancies, 65 `.docx` CVs.
  - The annotations rank the 5 vacancies **for each CV** (CVs 1-30, 2 annotators).
  - The README calls the file `annotations-for-the-first-30-cvs.txt`, but the repo has `annotations-for-the-first-30-vacancies.txt`.
- **Labelling kit:** the build printed `pairs 40; sheet rows 280; strata {'partial': 16, 'strong': 12, 'weak': 12}`. The workbook reloads with openpyxl and has 3 sheets with the right headers.
  - I grepped the 40 CVs for `@ / linkedin / github / name`: 4 harmless hits ("shown in my LinkedIn profile", "published on my Github", "cluster products by name"), and no URLs or contacts.

## 3. Not done / problems

1. **The requirement list is a DRAFT.** The labelers must confirm it (guide step 0). If they change it, I rerun `build_labelling_kit.py` to rebuild the sheet. Their edits to the CSV are kept, because the script reads the CSV.
2. **Strata are a rough guide only** (keyword + years). Some "strong" CVs will not be strong for niche requirements: J1 asks for Pyro/PyMC3, SageMaker and PySpark. This is expected, and the labels decide.
3. **J3 and J1 draw from the same Djinni keyword** ("Data Science"; there is no ML keyword in Djinni). J3's "strong" CVs may be data scientists rather than ML engineers. I didn't filter on Position, because the task allows only keyword and years.
4. **Experience Years 11** is Djinni's top bucket (probably "10+", not verified). One J4 CV has an 11 in its header while its text says "10 years".
5. **Some Djinni `Position` values are not English** (for example "Разработчик Python"). The CV bodies are English.
6. **MIT notice:** `data/processed/cvs` and `jobs` are copies of Djinni data. Before the push, the MIT copyright notice must be added; the HF cards do not include the text.
7. **Not run:** the full val *without* the schema for the LoRA, because the 30-item check showed identical raw output. The 0.892 vs V2's recorded 0.908 is therefore not a same-setup comparison. V2 used llama-cpp-python with no schema.
8. The Kaggle and Vanetik raw files are downloaded but not yet parsed (that belongs to the Reader task).

## 4. Questions for the Brain

1. Should the schema guardrail be **on by default** for every Matcher call? I recommend yes: it removes the invalid → UNCERTAIN path at no accuracy cost for the LoRA and adds about 0.3 s per call.
2. The LoRA turns gold-UNCERTAIN into MISSING (9/39) or MET (4/39) on val. Should the validator / Judge task target this, for example "MET without a strong quote goes to review"? That would be an evidence-based input for matcher-v2.
3. **MIT notice:** is a `data/processed/DJINNI_LICENSE.md` with the MIT text plus the citation enough? I can draft it when the push is approved.
4. **Kaggle data:** the IT category has almost no data/ML resumes. Should we use it only for the Reader (PDF → text against `Resume_str`), not for matching evaluation?

## 5. Suggested next step

1. Labelers do step 0 (confirm requirements). I rebuild the sheet, and they label (about 3-4 h each).
2. In parallel: the Matcher station endpoint on port 8010, with the schema on, plus the deterministic validator (quote substring + position, not_documented → review). Measure it on val with the existing `lora_k` outputs (offline re-scoring, no new GPU run).
