# T19 report — recruiter flow: one job, up to 3 candidates, evidence comparison, human-approved letters

## In plain words
- **A second page, http://127.0.0.1:8010/ui/recruiter.html, turns HireSignal into a small recruiter product.**
  1. Paste a job, or load a card.
  2. Confirm or edit its requirements, and merge rows to fix the "or similar" split.
  3. Upload 1–3 CVs, each checked against the same card, one after another, with live progress.
  4. Compare them in an evidence matrix (✓ / ✗ / ?, click for the CV quote), then choose Invite / Reject / Hold for
     each candidate. The letter appears as an editable preview; the recruiter approves it, can reveal the name and
     e-mail, and opens their own mail app.
- **There is no ranking, no "best match" and no automatic e-mail.** Columns follow the gate's outcome, then the upload
  order. The reasons are in `docs/RECRUITER_FLOW.md`.
- **No pipeline change:** the n8n workflow, prompts, models, gate and `/report` contract are untouched. The T16 page
  still works (only a link was added to its header).
- **Tested end to end** with 3 dataset CVs against job J4: one invite, one review, one reject. 4 screenshots are in
  `docs/ui/recruiter/`.
- **Pushed** on its own branch `v3-recruiter-flow`, created from `v3-final` after T18's push (`6ef313d`). The
  secret-scan value that blocked T18 was removed by the Approver's option (b); the scan is now 0.

## 1. Done (files)
- **`services/recruiter.py` (new):**
  - card validation (each row with `RequirementIn`; the webhook's `requirements` format,
    `confirmed_by: "recruiter (UI)"`) and merge (" or ", union of terms, the smallest min_years);
  - the batch (1–3 CVs, the same card, one after another through T16's `forward_to_n8n`; the T16 lock, so `/ui/run`
    and a second batch get 409; results and `batch_summary.json` under `private/batches/<id>/`; file names never sent
    or stored);
  - status: the T16 live progress of the running candidate, counts as facts, and a column order that never uses the
    score;
  - letters (gate letter / recruiter-form letter from `eval/outbox` / the existing human-decision `/report` called in
    process);
  - approve (letter to `eval/outbox/<decision>/recruiter_<batch>_<label>.json` plus an audit line);
  - identity (only after an approved invite / reject; name and first e-mail from `private/<cv_id>.json`, returned to
    the page only; the audit line says only `identity_revealed: true`).
- **`services/ui.py`**: includes the recruiter routes (before the static mounts). No other change.
- **`ui/recruiter.html` (new)**: a stepper (Job · Requirements · Candidates · Compare & decide), an editable card
  table, candidate rows with live agent chips and an overall bar, the column cards, the evidence matrix with cell
  details, "Needs your eyes", the details drawer with "How it was decided" and the decide / letter / approve / reveal
  / mailto box.
  - T16 palette, keyboard reachable (buttons, focus rings, Esc closes the drawer).
  - Laid out for 1366 px.
  - An empty or error state for each step.
- **`ui/index.html`**: one header link to the recruiter page. Nothing else changed.
- **`demo/recruiter_P32_cv.txt`, `demo/recruiter_P35_cv.txt`**: J4 gold pairs from the Djinni dataset (MIT,
  anonymised at source), so the demo has 3 candidates for one job.
- **`tests/test_recruiter.py` (new, 10 tests):**
  - card validation (format, clear errors, empty list);
  - merge;
  - max 3 CVs and 409 when busy (batch and `/ui/run`);
  - the same card for every candidate, the token sent to n8n but never in replies, the summary or logs, and file
    names never forwarded or stored;
  - order by outcome, then upload, never the score;
  - facts as counts;
  - approve, then identity reveal only after Approve: identity never in logs, the audit log, the letter file or n8n;
  - hold (no letter, no identity);
  - review case → recruiter form;
  - pages hold no token and no ranking words, and the two pages link to each other.
- **Docs**: `docs/RECRUITER_FLOW.md` (the steps, why there is no ranking or automatic e-mail, the endpoints), plus a
  "Recruiter flow" section in `demo/README.md` and `INSTALL.md`.

## 2. Evidence (checks)
1. **Tests.** `pytest -q` → **532 passed, 1 skipped** (10 new; the T16 tests still pass).
2. **Webhook unchanged** (`eval/results/2026-10-19_recruiter_checks/webhook_direct/`, direct webhook with the cards):
   **P50 invite 94** (execution 87), **P02 reject 13** (execution 88), the same as T16.
3. **End to end** through the real page, driven by Chrome DevTools (Node 24 script): demo job J4 + its card →
   confirm (6 requirements, 3 must) → the 3 J4 CVs → Run.
   - **A (P50) invite, must-haves 3/3**; **B (P32) review, 3/3**; **C (P35) reject, 0/3**. Column order A, B, C.
   - No file name was shown on the page (checked).
   - Screenshots in `docs/ui/recruiter/`: `1_step2_card_editor.png`, `2_step3_running.png` (A in the Matcher, 3/6),
     `3_step4_matrix.png` (an unclear cell opened, "Needs your eyes"), `4_letter_preview.png`.
   - After that: Approve → `eval/outbox/invite/recruiter_20261019-123916-7ce0_A.json`, and the audit log gained 2 lines
     (`approved`, `identity_revealed`). There are no identity values in either line. The dataset CV has no name, and
     the page says so.
   - **Override** (C: gate reject → recruiter invite): a checked letter (`source: llm`) from the existing
     `/report` human path.
   - **Review** (B): "decide in the recruiter form first", with the form link.
4. **The T16 page `/ui/` still works:** invite sample through the page → **invite 94** (execution 92).
5. Optional run with Yassine's CV: **not done** (to save time).
- **Secret scan, first run** (`eval/results/2026-10-19_secret_scan_t19/scan.json`, 3,607 files):
  - `.env` secret values 0, key patterns 0;
  - identity hits in `ui/`, `docs/ui/`, `demo/` and the new code / tests: **0**;
  - **1 unexplained**: the same GitHub handle in `tasks/T14_final_polish.md` as in T18.
- **Secret scan after the Approver's option (b)** (`eval/results/2026-10-19_secret_scan_push/scan.json`, 3,610 files,
  T19 files included): `.env` values **0**, key patterns **0**, identity unexplained **0** → **PASS**.
- **Tests on this branch before the commit:** `pytest -q` → **532 passed, 1 skipped**.
- **Git (G):**
  1. T18 pushed first: `v3-final` `a93368d..6ef313d` (`git ls-remote` shows `6ef313d`).
  2. `git checkout -b v3-recruiter-flow` from `6ef313d`.
  3. Commit "T19 recruiter flow: 1 job, up to 3 candidates, evidence matrix, human-approved letters"; this commit
     also holds the 2-line router include in `services/ui.py`, the header link in `ui/index.html` and the
     "Recruiter flow" paragraphs in `INSTALL.md` / `demo/README.md`, which T18 left out.
  4. `git push -u origin v3-recruiter-flow`; the remote hash was checked with `git ls-remote` after the push.

## 3. Not done / problems
- **Override vs review:** an override of a gate invite / reject uses the existing human-decision `/report` path.
  `/report` already supports `decided_by: human` since T13, so no contract change was needed.
- **A review case needs the n8n form first;** the page then loads the letter n8n wrote. A review candidate can't be
  decided inside the page alone, because the waiting n8n execution owns that decision.
- **Job files:** text and .txt only (the Reader does not return document text).
- **The progress chips** show the running candidate only; finished candidates show their outcome and time.
- **Time spent:** about 1 h 45 min, inside the 4 h box.

## 4. Questions for the Brain
1. Should "Hold" also be offered for review cases? It is today: it writes an audit line, and the n8n execution keeps
   waiting.

## 5. Suggested next step
Record the recruiter flow for the demo video
(about 4 minutes for 3 text CVs).
