# T04 — Station API v1 (Reader, Profile, Job Agent, Matcher) reused from V2

Read `CLAUDE.md` first. Goal: the first four stations run as HTTP endpoints that n8n can call (n8n itself comes in T05). Reuse V2 code (rule 6 header on every copied file), adapt it, keep it simple.

## Part 0 — Housekeeping
- Add the MIT licence notice for the Djinni data we copied: `data/processed/NOTICE_DJINNI.md` (licence text + dataset links + paper citation).
- Labelling must be blind: split `data/labels/labelling_sheet.xlsx` into `labelling_sheet_A.xlsx` and `labelling_sheet_B.xlsx` (each has only its own decision/quote/outcome columns; the `job_requirements` sheet in both). Add `scripts/merge_labels.py` that merges A and B back and computes agreement (percent agreement + Cohen's kappa, per requirement decision and per outcome). Update `LABELLING_GUIDE.md` to say each labeler gets their own file.

## Part A — One FastAPI app on port 8010 (`services/api.py`)
Endpoints (JSON in/out, pydantic models in `services/contracts.py`):
| Endpoint | Input | Output | Reuse from V2 |
|---|---|---|---|
| `GET /health`, `GET /ready` | — | status; `/ready` also checks llama-server on 8090 | backend/main.py (idea only) |
| `POST /reader` | CV file (PDF, DOCX, TXT, JPG, PNG) | `cv_id` (random), text, sections, read path, OCR confidence, warnings | agents/reader/ |
| `POST /profile` | `cv_id` + text | anonymised text + placeholder report (counts only) + parsed profile (skills / education / experience with quotes). Identity is written ONLY to git-ignored `private/<cv_id>.json`, never returned | agents/profile/ (keep V2's V2-only fixes: chunk 800 chars, max tokens 768) |
| `POST /job` | job text | requirements card (id, kind must/nice, category, min_years, verbatim source sentence) + injection flags | agents/job/ + the injection filter in integration/upstream.py |
| `POST /match` | anonymised CV text + ONE requirement | decision MET/MISSING/UNCERTAIN, basis, verified quotes with spans, explanation, knowledge refs used, review reasons, model + prompt id | matcher/ (prompt p1 = `prompts/matcher/v1.md`, our `services/matcher/schema.json`, BM25-ESCO k=3 knowledge provider you already copied) |

Model calls go to llama-server (8090) with the per-request LoRA scale: 0 for Profile and Job, 1 for Matcher. All URLs, model names, timeouts in `.env` / `config/.env.example`.

## Part B — Validator: evidence checks only
V2's validator v2 overfit val (test macro-F1 0.678 vs raw 0.887). For v1 keep only checks that are rules of evidence, not tuned on val: (1) every quote must be an exact CV substring (span verified), MET without a verified quote -> UNCERTAIN + review reason; (2) years: code compares the years in the quoted evidence with `min_years` when present. List in your report every V2 validator rule you did NOT keep and why (one line each). Code in `services/matcher/validate.py`.

## Part C — Anonymiser fix (Decision 17)
V2 does not hide gendered words (`agents/profile/detect.py:244`). Add gendered pronouns and gendered job/role words (EN + FR, word boundaries, case-insensitive; e.g. she/he/her/his/him/hers, Mr/Mrs/Ms, "Ingénieure"/"Ingénieur" style feminine forms) to the masking with neutral placeholders. Add tests that show it masks them and does NOT break words that contain them (e.g. "the", "theory", "where", "hero", "chemistry").

## Part D — Tests and a real smoke run
1. Port the V2 unit tests for the code you copied (mock LLM) + your new tests. All must pass: report counts.
2. `scripts/start_stack.ps1` with `-Stop`: starts llama-server (8090) and the station API (8010), waits for `/ready`. (n8n keeps its own script.)
3. Real-GPU smoke, results in `eval/results/<date>_api_smoke/`: one Kaggle IT PDF through `/reader`; one Djinni CV from `data/processed/cvs/` through `/profile`; `data/processed/jobs/J2.txt` through `/job`; then `/match` for every requirement of that job on that CV. Save inputs, outputs and per-endpoint timings. Check: no identity in any response, quotes verified, valid JSON everywhere.
4. Tesseract is still not installed: OCR tests may skip; say which.

## Report
`tasks/T04_report.md` (format in CLAUDE.md). Leave llama-server and the API stopped at the end.
