# T05 report — first end-to-end run in n8n (walking skeleton)

Date: 2026-10-18. No git commands were run. All model runs are **real-GPU** (RTX 4050 Laptop 6 GB, llama.cpp b11139, Qwen3-4B Q4_K_M with the Matcher LoRA).

**Summary:**
- A CV file and a job text go into n8n through `POST /webhook/hiresignal`. Every station runs as its own n8n node, and a JSON result comes out.
- I ran 3 webhook runs (P15, P35, Kaggle PDF + J4) and 1 Manual-trigger run.
  - All of them returned HTTP 200 with valid JSON.
  - Every `/match` call used LoRA scale 1.
  - The `/match` calls ran **one at a time**.
  - **0 identity values** were found in the stored n8n execution data.
- The error path writes its log line.
- Tests: **325 passed, 6 skipped.** The skipped tests are OCR tests, because Tesseract is still missing.
- Final state: n8n is **running** on :5678. llama-server and the API are **stopped**: ports 8010 and 8090 are free, and the GPU shows 0 MiB.

## 1. Done

**Part 0: API changes**
- `/reader` writes the raw Reader output only to git-ignored `private/<cv_id>.reader.json`. It returns `cv_id` plus metadata: `text_chars`, the length of each section, read path, layout, OCR confidence and warnings. The raw text is never returned.
- `/profile` takes only `{cv_id}` and loads the text itself. It returns 404 if `/reader` was not called first.
  - `cv_id` is still pattern-checked, so it cannot be used as a path.
  - Files: [services/api.py](../services/api.py), [services/contracts.py](../services/contracts.py).
- Every station response now has two flag lists: `review_reasons` (send to a human) and `info_flags` (shown, never block).
  - `/reader`: review = `reader:low_confidence_or_little_text`; info = `reader:<warning>`.
  - `/profile`: `profile:name_not_found` is an **info flag when no contact data was found at all** (no email, phone, URL or address), and a review reason otherwise.
  - `/job`: the benign "no requirement section" warning becomes the info flag `job_agent:no_requirement_section`.
  - `/match`: `info_flags` is empty for now ([validate.py](../services/matcher/validate.py)); every evidence rule is still a review reason.
- Case-sensitive honorific matching is kept, as approved. It is documented in [services/profile/gender.py](../services/profile/gender.py) and in T04.
- Tests updated and added in [tests/test_api.py](../tests/test_api.py):
  - the Reader never returns raw text;
  - `/profile` without a Reader output gives 404;
  - `name_not_found` goes to `info_flags` without contact data and to `review_reasons` with contact data.
- [scripts/api_smoke.py](../scripts/api_smoke.py) is updated to the new `/profile` contract.

**Part A: the n8n workflows**

Built from a generator script, imported with the n8n CLI into the running n8n (`.n8n/`), run, then exported back from n8n.

- **HireSignal v1** (`HsV1Main00000001`, [n8n/hiresignal_v1.json](../n8n/hiresignal_v1.json)):
  - Triggers: Webhook `POST /webhook/hiresignal` (multipart `cv` + `job_text`, response from a node) and Manual demo (Read sample job → Extract text → Read sample CV → shaped like the webhook input).
  - Nodes after the triggers: Normalize input → HTTP `/reader` → HTTP `/profile` ‖ HTTP `/job` → Merge → Split requirements (Code) → **Loop requirements (1 at a time)** (Loop Over Items, batch size 1) → HTTP `/match` → Aggregate → **TEMP outcome** (Code) → Respond to Webhook.
  - The Manual demo reads pair P15 (J2) through relative paths.
- **TEMP outcome:** labelled temporary in the node name, the code comment and the output field `outcome_step`.
  - It applies the Decision 5 formula `round(100·Σ(w·v)/Σw)` (must 2, nice 1; MET 1, UNCERTAIN 0.5, MISSING 0) and the task's rule: any review reason → review; else a must-have MISSING → reject; else score ≥ 80 → invite; else review.
  - It returns per-requirement decisions, quotes, flags, the score, the outcome with its reason, a "request human review" note on rejects, and timings.
- **Robustness:**
  - Every HTTP node has a timeout (reader 120 s, profile 900 s, job 600 s, match 180 s) and Retry On Fail with 2 tries, 5 s apart.
  - Its error workflow is **HireSignal errors** (`HsV1Errors000001`, [n8n/hiresignal_errors.json](../n8n/hiresignal_errors.json)): Error Trigger → Code "Log line" (time, workflow, node, execution, message; no CV data) → Convert to File → Read/Write Files (append to `eval/logs/n8n_errors.log`).
- **Export:** both files are exported with the n8n CLI, then cleaned by [scripts/clean_n8n_export.py](../scripts/clean_n8n_export.py).
  - n8n's export included the owner's **name and e-mail** (`shared` block). The script removes it, asserts that no e-mail address and no credential is left, and sets `active: false`.
  - The cleaned files re-import into an **empty** n8n data folder (both "Successfully imported").
- [n8n/README.md](../n8n/README.md) covers the start order, CLI import and activation from our portable Node, export and cleaning, the webhook URL with a curl example, and the Manual demo.
- [scripts/n8n_cli.ps1](../scripts/n8n_cli.ps1): runs the n8n CLI with our Node and data folder (process environment only).
- [scripts/start_n8n.ps1](../scripts/start_n8n.ps1): now runs n8n from the repo root (for the relative sample paths) and sets, for this process only:
  - `N8N_RESTRICT_FILE_ACCESS_TO` = `data\processed;eval\logs`;
  - `N8N_DIAGNOSTICS_ENABLED=false`;
  - `N8N_USE_WORKFLOW_PUBLICATION_SERVICE=false` (see §3.1).

**Part B:** [scripts/n8n_e2e.py](../scripts/n8n_e2e.py) and results in [eval/results/2026-10-18_n8n_e2e/](../eval/results/2026-10-18_n8n_e2e/) (`NOTES.md`, `config.json`, per-run result and execution files, `summary.json`, `manual_trigger_P15_result.json`, `error_path/`).
- For each run, the script calls the webhook. It then reads the execution from n8n's SQLite in read-only mode: status, per-node timings from runData, and an identity search.

## 2. Evidence

**Tests** (mock): `pytest tests/` gives **325 passed, 6 skipped** (OCR: Tesseract missing). That is T04's 321 plus 4 new API tests.

**Webhook runs** (n8n executions 7, 8, 9; TEMP rule):

| run | input | wall s | /profile s | /job s | /match | outcome | score | review_reasons |
|---|---|---|---|---|---|---|---|---|
| P15 | Djinni CV (pair P15) + J2 | 56.8 | 29.0 | 6.6 | 7 × 2.2–4.1 s (20.4 s) | reject (must MISSING r1, r2, r3, r6) | 43 | none |
| P35 | Djinni CV (pair P35) + J4 | 40.5 | 1.6 | 9.2 | 13 × 2.0–2.6 s (28.4 s) | reject (must MISSING r1, r3) | 13 | none (info: `profile:name_not_found`) |
| Kaggle | `10089434.pdf` + J4 | 196.6 | 146.6 | 9.0 | 13 × 1.9–4.9 s (39.7 s) | review | 13 | `profile:partial_extraction_requires_review`, `match:r12/r13:evidence_not_in_cv` |

- These are per-node times from n8n's runData. The Reader, Merge, Code, Aggregate and Respond nodes each take under 0.2 s.
- **Manual trigger** (CLI `n8n execute`): every node ran, with the same 7 decisions as webhook run P15, outcome reject, score 43.

**Checks** (from `checks` in `<run>_execution.json`):
- HTTP 200, valid JSON and execution status `success` in all 3 runs.
- `all_match_lora_scale_1`: True in all 3 runs.
- **Identity:**
  - Every value of `private/<cv_id>.json` was searched in the stored execution data, as text and as decoded base64 strings: P15 0/2, P35 0/0, Kaggle 0/3 found.
  - Every raw CV line that the anonymiser changed was also searched: P15 4 lines, Kaggle 5 lines, 0 found.
  - **I did not open the executions in the n8n UI.** I searched the same data in n8n's database. The Approver can still check in the UI (executions 7–9).
- **Sequential `/match`:** execution 7 has 7 HTTP `/match` runs and 8 Loop runs. The server times (2.2–4.1 s) add up to the node time, so the calls do not overlap.

**Error path:**
1. I stopped only the station API (port 8010 closed) and sent P35.
2. The webhook returned `HTTP 500 {"message":"Error in workflow"}` after 5.5 s (2 tries, 5 s apart).
3. Execution 11 (HireSignal v1) ended in error, and execution 12 (HireSignal errors) succeeded.
4. The log line in `eval/logs/n8n_errors.log` (copy in `error_path/n8n_errors_log.txt`):
   ```
   2026-10-18T08:47:37.331Z	workflow=HireSignal v1	node=HTTP /reader	execution=11	message=The service refused the connection - perhaps it is offline
   ```
5. I then restarted the API (`start_stack.ps1`, "Station API ready").

## 3. Not done / problems

1. **n8n 2.43 activation on SQLite:**
   - Publishing through the CLI left a record `in_progress` in `workflow_publication_outbox`. n8n's SQLite query never reclaims it (the stale-reclaim path exists only for Postgres), so the webhook stayed "not registered".
   - Fix without touching n8n's DB: `N8N_USE_WORKFLOW_PUBLICATION_SERVICE=false` in `start_n8n.ps1`, n8n's classic activation. The log then shows `Activated workflow "HireSignal v1"`.
   - The stuck record is still in the DB, and it is harmless with this setting.
2. **The error workflow must be published in n8n 2.x.** The first test (execution 10) logged `Workflow "HsV1Errors000001" is not active`. The README now publishes it.
3. **The n8n HTTP node's "batching" option does not make calls sequential**: it only spaces requests out. Executions 1–6 sent all `/match` calls at once (they queued on llama-server). I replaced it with Loop Over Items; executions 1–6 are superseded.
4. **The uploaded CV file stays in n8n:**
   - n8n's binary store keeps it (`.n8n/storage/.../binary_data/`, git-ignored), and the execution data keeps its file name.
   - The CV enters through the n8n trigger, so this is unavoidable. A real file name like `John_Smith_CV.pdf` would sit in the execution metadata. Pruning the stored executions would limit this.
5. **Anonymiser false positive (V2 code; not fixed, out of scope):**
   - On P15, the header name detector took "BI Tools" (a CV bullet) as the candidate's name, then hid every part of it.
   - Result: "Power BI" became "Power [NAME]" and "ETL Tools" became "ETL [NAME]". This destroys evidence for the Matcher. It happens because a CV with no headings is treated as all header.
6. **Matcher errors in these runs** (single runs, for the Judge task):
   - P15 r6 "GCP or other cloud providers": MISSING/contradicted, while the quote itself says "Azure and AWS services".
   - P15 r7 "Good spoken English": MET with 3 quotes that do not mention English. This is the same pattern as the T04 smoke run.
7. **The task called P15 "expected strong" and P35 "expected weak",** but `data/labels/pairs.csv` has **both as stratum "partial"** (P15: Data Engineer, 2 years; P35: Python, 2 years). I ran them as asked. Both were rejected by the TEMP rule.
8. **Job Agent on J4:** 13 requirements, 3 must and 10 nice, because the nice list was split per skill. Our DRAFT list for the labelers has 6.
9. **To run the Manual trigger from the CLI while n8n was running,** I used task-broker port **5680** for that one CLI process, because 5679 is used by the running n8n. No lasting change. In the UI, "Execute workflow" needs no extra port.
10. **Kaggle `/profile` took 146 s** (2 chunks cut at 768 tokens). Not changed, as you instructed.

## 4. Questions for the Brain

1. Fixing the "BI Tools" name false positive (§3.5) touches V2's anonymiser rules. Should it be a separate small task? Two options: skip header-name detection when the CV has no section headings, or add tech words ("tools", "bi", …) to `NOT_NAME`. It should be measured on the 40 CVs for leaks and false hits.
2. Should n8n prune stored executions, for example `EXECUTIONS_DATA_MAX_AGE`, or not keep binary data for successful runs, so that uploaded CVs do not pile up in `.n8n/storage`? Note that this would also remove the executions we inspect for evidence.
3. Is `N8N_USE_WORKFLOW_PUBLICATION_SERVICE=false` acceptable? The alternative is to delete the stuck outbox row in n8n's SQLite, which is DB surgery.
4. Should the J4 requirement split (13 requirements, mostly nice) be aligned with the labelers' list before the end-to-end evaluation?

## 5. Suggested next step

1. **Judge task:** the NLI Judge (DeBERTa, base checkpoint per the T01 inventory) as station 6. Add it as an n8n node after `/match`, and make the confidence check its first input. The false-MET cases here (P15 r7) and in T04 are ready-made test cases.
2. Then replace `TEMP outcome` with the Outcome gate.
