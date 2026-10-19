# T03 — Structured output, full val run, real data + labelling kit

Read `CLAUDE.md` first. Answers to your T02b questions: 1) stay on b11139, never change Windows security settings. 2) do NOT change the Matcher prompt now (the LoRA was trained on it); fix the template-copying with constrained decoding instead (Part A). Matcher prompt iterations will come later from failures on real data. 3) yes, run the full val now (Part A), it gives us a traceable LoRA number that V2 does not have.

## Part A — JSON-schema constrained decoding + full val
1. Write the Matcher output JSON schema in `services/matcher/schema.json` (decision enum MET/MISSING/UNCERTAIN, basis, evidence list of quotes, explanation: read V2 `matcher/json_schemas/` and `matcher/schemas.py` and stay compatible).
2. Send it with each request (`response_format` json_schema, or llama-server's `json_schema`/grammar field for b11139; check its docs/--help and cite).
3. Re-run the same 30 items, base and LoRA with knowledge, with the schema. Report: did base valid-JSON go to 1.000? Did LoRA results stay the same (item-by-item diff)? Log it in `prompts/PROMPT_LIBRARY.md` as a serving-level guardrail (technique: structured output / constrained decoding; failure: template copying; before/after numbers).
4. Full bench-v1 **val** (all 202 requirements), base vs LoRA, both with BM25-ESCO k=3 knowledge and the schema. Same metrics as T02b + per-class F1 + confusion matrix. Results in `eval/results/<date>_val_full/`. Do NOT touch the test split (it stays sealed for the final evaluation). Note in the summary that bench-v1 is synthetic.

## Part B — Real data (download + data card; no labelling)
Save raw data under `data/raw/` (git-ignored). For every source, read the official page and cite the licence.
1. **Djinni (English):** Hugging Face `lang-uk/recruitment-dataset-candidate-profiles-english` and `lang-uk/recruitment-dataset-job-descriptions-english` (MIT per the UNLP 2024 paper; confirm on the dataset cards). Report rows, columns, top "Primary Keyword" values, CV length stats, how many CVs still contain personal names/contacts (rough regex count).
2. **Kaggle Resume Dataset** `snehaanbhawal/resume-dataset` (CC0, confirmed by the Approver on Kaggle): use the Kaggle API if `~/.kaggle/kaggle.json` exists; if not, STOP this item and ask the Approver to download it. Report the number of PDFs per category, especially INFORMATION-TECHNOLOGY.
3. **Vanetik vacancy-resume dataset** (GitHub `NataliaVanetik/vacancy-resume-matching-dataset`, GPL-3.0): read its 5 vacancies and report their job domain. Download only if they are tech jobs.
4. Write `data/DATA_CARD.md`: per source: link, licence, size, format, what we use it for, known limits.

## Part C — Labelling kit for 40 real CV x job pairs (prepare only; humans label)
1. Pick 4 Djinni English job descriptions with clear requirements: Data Scientist, Data Engineer, ML Engineer, Python Backend Developer. Save as `data/processed/jobs/J1.txt`..`J4.txt` with their Djinni ids.
2. For each job pick 10 Djinni English CVs with a related Primary Keyword, spread so we expect roughly 3 strong / 4 partial / 3 weak candidates (use only Primary Keyword and Experience Years as a rough guide; do NOT use any model to pick). Save as `data/processed/cvs/<cv_id>.txt`. 40 pairs total, list in `data/labels/pairs.csv`.
3. For each job, draft the requirement list (6-8 items, must/nice, each with the exact job sentence it comes from) in `data/labels/requirements_draft.csv`, marked DRAFT: the labelers confirm or edit it before labelling.
4. Build the labelling sheet `data/labels/labelling_sheet.xlsx`: one row per (pair, requirement) with columns for labeler A and labeler B (decision MET/MISSING/UNCERTAIN + CV quote), plus a per-pair sheet for the overall outcome (invite / review / reject) by A and B. No model predictions in the sheet (blind labelling).
5. Write `data/labels/LABELLING_GUIDE.md` (max 1 page, simple English): what MET/MISSING/UNCERTAIN mean (MET needs a CV quote), how to choose invite/review/reject, examples, estimated time.

## Report
`tasks/T03_report.md` (format in CLAUDE.md).
