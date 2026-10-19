# T19 — Recruiter flow: one job, up to 3 candidates, evidence comparison, human-approved letters

Approver: Yassine (2026-10-19). Start **after T18 is pushed**. Time box **about 4 hours**; at 4.5 h stop and report what
is done. Work on a **new branch** (part G).

## Why
Make the demo feel like a real recruiter product, while keeping V3's principles: same requirements for every
candidate, decisions backed by CV evidence, and **a human decides**. This is a view and workflow layer only.

## Hard limits (read first)
- **No change** to the n8n workflow, prompts, models, gate settings, Matcher/Judge/Report logic, or the existing
  station endpoint contracts. New endpoints are additive (like T16). The final evaluation numbers must stay valid.
- **The T16 page `/ui/` must keep working unchanged** (it is the demo fallback). Build the new flow as a second page,
  `ui/recruiter.html`, served at `http://127.0.0.1:8010/ui/recruiter.html`, with a link between the two pages.
- **No score ranking, no "best match" label, no percentage leaderboard.** (Reason, for the docs: our evaluation
  measured per-requirement decisions and outcomes, not ranking quality; the score depends on how the job was split;
  candidate ranking is high-risk under the EU AI Act; the recruiter must decide.)
- **No automatic email sending.** No SMTP, no mail API, no stored mail credentials.
- Offline, no CDN, no new dependency unless unavoidable (say so in the report). V1/V2 ports untouched.
- Personal data stays in `private/` (git-ignored). Use demo/dataset CVs for screenshots.

## The flow (stepper header: 1 Job · 2 Requirements · 3 Candidates · 4 Compare & decide)

### Step 1: Job
- Paste the job text or upload a .txt. Accept PDF/DOCX job files only if the existing Reader can already turn them into
  text without changes (check; if not, text and .txt only).
- Or load an existing requirements card (.json), which skips step 1's extraction.
- Button **Extract requirements**: calls the existing Job Agent (station `/job`, same prompt v2) once and shows the card.

### Step 2: Confirm requirements (the recruiter's card)
- Editable table: requirement text, **must / nice** toggle, min years, skill terms; delete row, add row.
- **Merge selected rows** into one requirement (texts joined with " or ", union of skill terms). This lets the
  recruiter fix the known "X, Y or similar" splitting without touching the Job Agent.
- **Confirm** produces a card in exactly the format the webhook's `requirements` field already accepts (same schema
  as `demo/*_requirements_*.json`), with `confirmed_by: "recruiter (UI)"`. Validate it with the existing contract;
  show clear errors. Allow downloading the card.

### Step 3: Candidates (max 3)
- Upload **1 to 3** CV files, in the formats the Reader supports today (the Reader docstring says PDF, DOCX, scan,
  photo; check TXT; accept only what works). For images and scans, show a warning: "about 3 minutes per photo".
- Candidates are labelled **Candidate A / B / C** in upload order. **Do not show file names** in steps 3–4 (they can
  contain names).
- **Run**: a new additive endpoint (e.g. `POST /ui/batch`) runs the candidates **one after another** through the
  existing webhook, each with the **same confirmed card**. One batch at a time (409 if busy; also block `/ui/run` while
  a batch runs). Show a status row per candidate (waiting / running with the live agent timeline from T16 / done /
  error) and an overall progress bar.
- Save each result plus `batch_summary.json` under `private/batches/<batch_id>/` (results hold CV quotes).

### Step 4: Compare & decide
- **Top of each candidate column:**
  - the gate outcome badge (invite / review / reject) and "decided by: gate" or "needs the recruiter";
  - facts as counts: "Must-haves met X of N · unclear U · nice-to-haves met Y of M";
  - the badge **"All must-haves met"** when true.
- **Column order:** invite → review → reject, then upload order. Never order by score. (The gate score can appear only
  inside the candidate's detail view, labelled "gate score".)
- **Evidence matrix:** rows = requirements (must-haves first, card order), columns = candidates, cells ✓ met /
  ✗ missing / ? unclear. Clicking a cell shows the CV quote(s), the Matcher confidence, the Judge verdict and the
  reasons in plain words (reuse the T16 card rendering).
- **"Needs your eyes"** panel: every UNCERTAIN cell and every flag across candidates, in one list.
- **Candidate detail** drawer: the full T16 result view, including a collapsible "How it was decided" timeline.
- Review cases: the existing `review_form_url` button ("Open recruiter form"). The human decision there produces the
  checked letter, as today.

### Step 5 (inside step 4): Decision and letters, human-approved
- For each candidate the recruiter chooses **Invite / Reject / Hold**.
  - When the choice equals the gate's decision, show the letter the Report Writer already wrote.
  - For review cases, use the recruiter form path.
  - For an override of a gate decision: reuse the existing human-decision report path **only if** the station's
    current `/report` contract already supports a human decision; otherwise show "override: use the recruiter form /
    not supported in this version" and note it in the report. Do not change `/report`.
- The letter appears in an **editable preview**. **Approve** saves it to `eval/outbox/<decision>/` (git-ignored) and
  writes an audit line.
- **Reveal identity** (only after Approve, one click per candidate): shows the candidate's name and email from the
  existing identity store in `private/` (written by `/profile`), local only. Then an **"Open in my mail app"** button
  makes a `mailto:` link (recipient, subject, body). The human sends it. Identity values must never be logged, sent to
  n8n or written outside `private/`.
- **Audit log** `eval/outbox/decision_log.jsonl`: time, batch_id, candidate label, cv_id, system outcome, recruiter
  decision, letter file, identity revealed yes/no. No CV text, no identity values.

### Look and feel
Same palette as T16 (navy `#14213D`, off-white `#F6F5F1`, blue `#2E63C9`), system fonts, clean spacing, clear stepper,
keyboard accessible, readable at 1366 px laptop width. Plain English labels. Empty and error states for every step.

## Checks (write the results in the report)
1. `pytest -q` all pass; new tests for:
   - the batch endpoint (max 3, 409 when busy, same card sent for every candidate);
   - the card validation and merge;
   - no token in any reply, page or log;
   - identity values never in logs, the audit log or n8n;
   - no score-based ordering.
2. The webhook still gives the same outcomes as before: P50 + J4 card → invite 94; P02 + J1 card → reject 13
   (as in T16).
3. **End to end with 3 dataset CVs against one job card** (e.g. the J4 card plus 3 CVs from `data/processed` that have
   J4 gold, or the demo samples). Save 4 screenshots to `docs/ui/recruiter/`: step 2 card editor, step 3 running,
   step 4 matrix, letter preview. Dataset/demo data only.
4. The T16 page `/ui/` still works (invite sample).
5. Optional: Yassine's CV (`private/my_test/`) as one of the 3 candidates, with results and screenshots **only in `private/`**.

## Docs
- New section in `demo/README.md` and `INSTALL.md`: "Recruiter flow".
- A short `docs/RECRUITER_FLOW.md`: the steps, and **why there is no ranking or automatic email** (reasons above).

## G. Git: new branch (approved for this task only)
- After the checks pass and `scripts/secret_scan.py` gives 0, create the branch **`v3-recruiter-flow` from
  `v3-final`** (after T18's push), commit (`T19 recruiter flow: 1 job, up to 3 candidates, evidence matrix,
  human-approved letters`) and run `git push -u origin v3-recruiter-flow`.
- Never push to `main` or `v3-final` in this task, never force-push, never merge. If git asks for credentials, stop.
  Never write a token anywhere.

## Report
`tasks/T19_report.md` (usual format): what was built, files changed, check results, screenshots, time spent, the
commit hash and push result, and open questions.
