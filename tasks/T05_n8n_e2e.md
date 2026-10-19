# T05 — First end-to-end run in n8n (walking skeleton)

Read `CLAUDE.md` first. Goal: a CV and a job go into n8n, every station runs as its own n8n node, and a result comes out. Later tasks replace the temporary parts (Judge, Bias, Report, real Outcome gate).

Answers to your T04 questions: 1) yes, do it (Part 0). 2) `name_not_found` becomes an INFO flag, not a review reason, when the text has no contact data at all (Part 0). 3) yes: the Judge and the confidence check come right after this task. 4) yes, but later (separate task); do not change the profile limits now. 5) case-sensitive honorifics: OK, keep and document.

## Part 0 — Two small API changes
1. `/reader` stores the raw text only in git-ignored `private/<cv_id>.reader.json` and returns `cv_id` + metadata (no raw text). `/profile` takes `cv_id` and loads the text itself. No raw CV text passes through n8n. Update tests.
2. Split flags into two lists everywhere: `review_reasons` (send to human review) and `info_flags` (shown, do not block). `name_not_found` with no contact data found -> `info_flags`. Update tests.

## Part A — n8n workflow `HireSignal v1` (one node per station)
Build it in the running n8n (http://localhost:5678, data in `.n8n/`), then export it.
1. **Triggers:** Webhook `POST /webhook/hiresignal` (multipart: `cv` file + `job_text`) and a Manual Trigger that loads one sample pair from disk, for demos.
2. **Nodes in order:** HTTP `/reader` → HTTP `/profile` and HTTP `/job` (two branches) → Merge → split the requirements into items → HTTP `/match` per requirement (sequential, batch size 1: one GPU) → Aggregate → Code node `TEMP outcome` → Respond to Webhook (JSON).
3. **`TEMP outcome` (clearly labelled temporary, replaced by the Outcome gate later):** score = round(100 × Σ(w·v) / Σw) with must = 2, nice = 1 and MET = 1, UNCERTAIN = 0.5, MISSING = 0 (Decision 5 formula). Rule: any `review_reasons` → review; else any must-have MISSING → reject; else score ≥ 80 → invite; else review. Return per-requirement decisions, quotes, flags, score, outcome, timings.
4. **Robustness:** every HTTP node has a timeout and n8n "Retry On Fail" (2 tries, 5 s); an **error workflow** (`HireSignal errors`: Error Trigger → write a log line to `eval/logs/n8n_errors.log` with workflow, node, message, time) set as the workflow's error workflow.
5. **Export** both workflows to `n8n/hiresignal_v1.json` and `n8n/hiresignal_errors.json` (no credentials inside). Write `n8n/README.md`: how to import with the n8n CLI from our portable Node, how to activate, the webhook URL, the start order (`start_stack.ps1`, `start_n8n.ps1`).

## Part B — Real end-to-end runs (real-GPU)
Through the webhook (PowerShell or curl), save everything in `eval/results/<date>_n8n_e2e/`:
- pair P15 (J2, expected strong) and pair P35 (J4, expected weak) from `data/labels/pairs.csv`, CV text files as upload;
- one Kaggle IT PDF with job J4.
For each run: final JSON, n8n execution id, per-node timings, total time. Check: no identity in the n8n execution data (open the execution in n8n and search for the private values), valid JSON, every `/match` used LoRA scale 1.
Also test the error path once: stop the station API, send one request, confirm the error log line, restart.

## Report
`tasks/T05_report.md`. Leave n8n running; stop llama-server and the API at the end.
