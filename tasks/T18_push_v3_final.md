# T18 — Push the current version (T16 + T17) to the team branch `v3-final`

Approver: Yassine (2026-10-19). Short task. **Approved git actions for this task only:** commit on `v3-final` and
`git push origin v3-final`. Nothing else.

## A. Two small clean-ups before the push
1. **`rag/README.md`**: the one-liner says "ESCO + job postings". The corpus is ESCO only (T09 report). Change it to
   say ESCO only (docs fix, no code).
2. **pyarrow (T16 question 1), decision:** move `pyarrow` out of `requirements.txt` into a new
   `requirements-dataprep.txt` (only the old data-prep scripts need it, e.g. `scripts/djinni_stats.py`). Add a short note
   in `INSTALL.md`: "Data-prep scripts only: `pip install -r requirements-dataprep.txt`. On Windows with Smart App
   Control, pyarrow may be blocked; the app itself does not need it." Do not change any system setting.
   (T16 question 2, direct webhook runs mixing into the page progress: no change, keep it as a known limit.)

## B. Checks (all must pass before any git command)
1. `pytest -q`: all pass (expected about 522 passed, 1 skipped).
2. `scripts/secret_scan.py` on exactly what will be staged: **0** secret values, **0** key patterns, **0 unexplained**
   identity values. Counts and paths only, never print a value.
3. `git check-ignore` confirms these are NOT staged: `private/` (including `private/my_test/` with Yassine's CV and
   results), `.env`, `models/`, `tools/`, `.n8n/`, `eval/outbox/`.
4. `docs/ui/` holds demo-sample screenshots and replay files only (no personal CV data). Check the two JSON files carry
   no identity values.

If any check fails: stop, do not commit, write it in the report.

## C. Commit and push
- Stay on branch `v3-final`. Commit everything since `a93368d`: T16 (`ui/`, `services/ui.py`, `tests/test_ui.py`,
  `docs/ui/`, docs updates), T17 (`docs/HIRE_SIGNAL_RAG_COMPLETE_EXPLANATION.md`, `tasks/T17_report.md`), the task files
  T16–T19 and their reports, and part A.
- Message: `T16 demo page, T17 RAG explanation, README/pyarrow clean-up`.
- `git push origin v3-final`.
- **Never** push to `main` or any other branch, never force-push, never rebase or merge. If the push is rejected
  (the remote has new commits), stop and report; do not pull or merge on your own.
- If git asks for credentials, stop and let a team member sign in. Never write a token in any file, config or log.

## Report
`tasks/T18_report.md`: checks with numbers, the commit hash, the push result. Then continue with `tasks/T19_recruiter_flow.md`.
