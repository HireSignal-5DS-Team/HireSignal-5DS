# n8n workflows

Exported from our local n8n 2.43.7 (`n8n export:workflow`, then `scripts/clean_n8n_export.py`, which removes the
owner's project block, i.e. name and e-mail, plus timestamps; no credentials are used by these workflows).

| file | workflow | id |
|---|---|---|
| `hiresignal_v1.json` | **HireSignal v1**: Webhook / Manual demo -> Normalize input -> HTTP /reader -> HTTP /profile ‖ (Confirmed requirements? -> Confirmed job card | HTTP /job) -> Job card -> Merge -> Split requirements -> Loop requirements (1 at a time) -> RAG lookup (T09) -> HTTP /match -> HTTP /judge (T07) -> Aggregate -> Bias Auditor (T11) -> Outcome input -> HTTP /outcome (T08) -> Report Writer (T12) -> Result -> Respond to Webhook -> Switch outcome -> invite/reject: Decided by gate, review: Wait for recruiter (form) -> Decided by human -> Outbox letter -> To JSON file -> Write eval/outbox file | `HsV1Main00000001` |
| `hiresignal_errors.json` | **HireSignal errors**: Error Trigger -> Log line -> To text file -> append to `eval/logs/n8n_errors.log` | `HsV1Errors000001` |

`HireSignal v1` has `HireSignal errors` as its error workflow (settings). Every HTTP node: timeout, Retry On Fail
(2 tries, 5 s). The outcome comes from the plain-code gate `POST /outcome` (T08, `services/outcome/gate.py`).

## Start order

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_stack.ps1   # llama-server :8090 + station API :8010 (waits for /ready)
powershell -ExecutionPolicy Bypass -File scripts\start_n8n.ps1     # n8n :5678 (foreground; data in .n8n\)
```
`start_n8n.ps1` runs n8n from the repo root (the Manual demo reads `data/processed/...` by relative path) and allows file
access only to `data\processed` and `eval\logs`. It also sets `N8N_USE_WORKFLOW_PUBLICATION_SERVICE=false`
(see `tasks/T05_report.md`: on SQLite a stuck publication record stopped the workflow from activating). This is a
**known n8n 2.43 + SQLite workaround**, accepted in T06. It also sets `EXECUTIONS_DATA_PRUNE=true` and
`EXECUTIONS_DATA_MAX_AGE=336`: stored executions, including the uploaded CV files, are deleted after 14 days.

## Import and activate (first time, or after editing the JSON)

n8n must be **stopped** while the CLI changes workflows (`start_n8n.ps1 -Stop`). `scripts\n8n_cli.ps1` runs the n8n
CLI from our portable Node (`tools\node`) with our data folder; nothing global is changed.
```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_n8n.ps1 -Stop
powershell -ExecutionPolicy Bypass -File scripts\n8n_cli.ps1 import:workflow --input=n8n\hiresignal_errors.json
powershell -ExecutionPolicy Bypass -File scripts\n8n_cli.ps1 import:workflow --input=n8n\hiresignal_v1.json
powershell -ExecutionPolicy Bypass -File scripts\n8n_cli.ps1 publish:workflow --id=HsV1Errors000001   # n8n 2.x runs only published error workflows
powershell -ExecutionPolicy Bypass -File scripts\n8n_cli.ps1 publish:workflow --id=HsV1Main00000001
powershell -ExecutionPolicy Bypass -File scripts\start_n8n.ps1     # log shows: Activated workflow "HireSignal v1"
```
Export after a change in the editor:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\n8n_cli.ps1 export:workflow --id=HsV1Main00000001 --output=n8n\hiresignal_v1.json --pretty
powershell -ExecutionPolicy Bypass -File scripts\n8n_cli.ps1 export:workflow --id=HsV1Errors000001 --output=n8n\hiresignal_errors.json --pretty
.venv\Scripts\python scripts\clean_n8n_export.py n8n\hiresignal_v1.json n8n\hiresignal_errors.json
```

## Webhook

**Shared secret (T13).** Every webhook request needs the header `X-HireSignal-Token: <WEBHOOK_TOKEN>`:
- the value lives in `.env` (git-ignored); `scripts/start_n8n.ps1` passes it to n8n's process only and allows `$env`
  in expressions;
- the "Check token" node lets the request through only when the header matches;
- otherwise "Refuse (403)" answers HTTP 403 `{"error": "missing or wrong X-HireSignal-Token header"}`;
- `scripts/n8n_e2e.py` sends the header automatically.


`POST http://localhost:5678/webhook/hiresignal`, multipart form: `cv` = the CV file (PDF, DOCX, TXT, JPG, PNG),
`job_text` = the job offer text, and optionally `requirements` = the recruiter-confirmed requirement card as JSON
text (T08b; e.g. `data/processed/jobs/J2_requirements.json`). With `requirements`, the Job Agent (`/job`) is skipped
and that list is used (info flag `job:requirements confirmed by recruiter`); without it, the Job Agent runs. The reply is the JSON of `Result` (outcome, score, per-requirement decisions
with verified quotes, review_reasons, info_flags, timings, execution_id). Example:
```bash
curl -X POST http://localhost:5678/webhook/hiresignal -F "cv=@data/processed/cvs/<cv_id>.txt" -F "job_text=<data/processed/jobs/J2.txt" -F "requirements=<data/processed/jobs/J2_requirements.json"
```
(Windows PowerShell 5.1 has no `-Form`: use `curl.exe` or `scripts\n8n_e2e.py`.) The Manual demo trigger runs pair P15
(J2) from disk: open the workflow in the editor and click "Execute workflow".

**Photos and scans (T10).** The same webhook takes a phone photo (JPG/PNG) or a scanned PDF as `cv`; no other trigger
is needed. `HTTP /reader` reads image pages with the Reader mode set by `READER_MODE` in `.env` (default `late` = late
fusion of Tesseract OCR and the local vision model `qwen2.5vl:3b` on our Ollama, `scripts/start_ollama.ps1`). If Ollama
is not running, the Reader falls back to OCR with a warning. The result JSON has a `reader` block: `mode`, `read_path`
(route per page: `text`, `ocr`, `vision`, `late`, `early` or `ocr (vision fallback)`), `pages` (vision model, latency,
`[unclear]` share, fusion counts, number of low-trust lines; never CV text), `ocr_confidence` and `review_reasons`.
A bad image (low OCR confidence, many `[unclear]` parts, many vision-only lines, cut vision output) gives a
`reader:*` review reason, and the gate then always answers `review` (rule 0), never a silent invite or reject.
Example: `.venv\Scripts\python scripts\n8n_e2e.py --out eval\results\<date>_n8n_e2e_photo --runs scan:K01_photo.jpg:P15 --cards`.
Timing on the 6 GB laptop GPU: with llama-server resident, one photo page takes ~2 min in `HTTP /reader` (the vision
model spills into shared memory). The node's timeout is therefore 900 s; with a free GPU a page takes ~10-15 s.

## RAG lookup (T09)

Inside the requirement loop, `RAG lookup` calls `POST /rag/search` with the requirement and the CV text and returns
`knowledge_refs` (3 ESCO concepts) + `retriever` + `skipped`. `HTTP /match` then sends those refs as
`knowledge_refs` (cv_text and requirement are taken from the loop item), so the knowledge the Matcher saw is visible
per requirement in the execution. Setup chosen on dev in T09 (V6): dense all-MiniLM-L6-v2 over ESCO chunk A in
Qdrant local mode, query = the requirement's skill terms, and no knowledge block (`skipped: true`, refs `[]`) when
every skill term is already written in the CV (env `RAG_*`, see `config/.env.example` and `rag/RAG_REPORT.md`).
The CV text is only used for that skip check, never as a query. The first lookup after an API start loads the
embedding model and builds the index (~20 s, real-GPU); later lookups take 4-20 ms.

## Bias Auditor (T11)

After the requirement loop (`Aggregate`), the `Bias Auditor` node calls `POST /bias` (station 5,
`services/bias/auditor.py`) with the card, the `/match` + `/judge` results and the pair's review reasons.
- **Leakage check.** It already ran inside `/profile`: protected lines (nationality, date of birth, marital status,
  native language, pronouns, religion, photo) and lines with only identity placeholders were removed from the
  Matcher's input, and protected words were masked (lexicon `config/bias_lexicon.json`). `/bias` returns the flags
  again (kind / rule / line, never the text).
- **Live swap test.** It runs only when the gate would decide automatically (invite or reject) and `BIAS_SWAP=on`. One
  counterfactual identity (the other gender, another origin) goes through the same Reader → anonymiser → leakage
  check:
  - if the Matcher input is byte-identical, nothing is re-run;
  - otherwise `/match` + `/judge` run again on the must-haves, and a changed decision gives `bias:swap_flip`.
- `Outcome input` adds the bias review and info flags to the pair flags. `bias:swap_flip` always sends the pair to
  review (gate rule 0).
- The result JSON has a `bias` block: `bias_flags`, `would_be_outcome`, `swap`, `review_reasons`.

## Report Writer (T12)

After `HTTP /outcome`, the `Report Writer` node calls `POST /report` (station 7, `services/report/`) with the
anonymised decision record: card text, decisions, verified quotes, Judge verdicts, the gate result, Reader flags and
the bias result. Qwen3-4B plain (LoRA scale 0, the same llama-server) writes:
- `recruiter_summary`;
- one line per requirement;
- `candidate_letter`: invite / reject only, and a reject letter names the missing must-haves and the right to a human
  review;
- `flags_for_recruiter`.

A code fact checker reads every report. One retry is sent with the checker's errors, then the template is used (info
flag `report:template_fallback`).
- The result JSON has a `report` block.
- The recruiter form (`Wait for recruiter (form)`) shows the summary, the requirement lines and the flags.
- `Outbox letter` writes the checked `candidate_letter` for gate decisions, and a short fixed letter when a recruiter
  decided after a review.
- The node's timeout is 300 s (a report takes ~10–25 s).

## Letter after a recruiter's decision (T13)

After the review form, "Decided by human" → "Report Writer (human decision)" (`POST /report` with
`decided_by: human`, outcome = the recruiter's decision) → "Human letter" → "Outbox letter". The letter is generated
and fact-checked like the gate's letters, with the template as fallback. It never calls the decision automated, and a
reject letter names the missing (or unclear) must-haves. The recruiter's free-text note is not sent to any model.

## Outcome branches (T08)

- **invite / reject** (decided by the gate): the result JSON is written to `eval/outbox/invite/` or
  `eval/outbox/reject/` as `<execution>_<cv_id>.json` (stands in for the e-mail). Rejects carry the reasons and the
  sentence "You can request a human review of this decision."
- **review**: the webhook reply contains `review_form_url`; the execution waits (Wait node, "On Form Submitted").
  The recruiter opens the URL, picks `approve-invite` or `reject` and may add a note; the execution resumes and writes
  the final decision with `decided_by: human` to `eval/outbox/<decision>/`. The form fields are `field-0` (Decision)
  and `field-1` (Note) if you submit it from a script: `curl -X POST "<review_form_url>" -F field-0=reject -F field-1=...`.
- `eval/outbox/` is git-ignored. `start_n8n.ps1` creates `eval/outbox/invite` and `eval/outbox/reject` (n8n needs the
  folders to exist) and allows file access to them.

