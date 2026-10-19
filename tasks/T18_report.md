# T18 report — push to `v3-final`

## In plain words
- **Both clean-ups are done, all checks pass, and the work since `a93368d` is committed on `v3-final` and pushed.**
- The first secret scan stopped the task: it found **1 identity value**, the Approver's own GitHub handle, in the
  repo URL that `tasks/T14_final_polish.md` contained (the same URL is in Yassine's CV, so the anonymiser had stored it
  as identity).
- **Approver's decision: option (b).** The URL was replaced with "personal repo (removed)" in
  `tasks/T14_final_polish.md` (and the shorter `<handle>/HireSignal` form in `tasks/T14_report.md`), in the new commit,
  **without rewriting git history**: the older commit `b7d1d1a` still contains it.
- The re-run scan: **0 / 0 / 0 unexplained → PASS.**
- T19 code (the recruiter flow) is **not** in this commit; it goes to its own branch `v3-recruiter-flow`
  (`tasks/T19_report.md`).

## 1. Done
- **A1.** `rag/README.md`: the one-liner now says "ESCO only, ICT skills subset, no job postings".
- **A2.** `pyarrow==26.0.0` moved from `requirements.txt` to the new `requirements-dataprep.txt`, with a header that
  explains why. There is a dated note in `requirements.txt`, and the note asked for in `INSTALL.md` §1. No system
  setting was changed. `pip check` → "No broken requirements found."
- **`scripts/secret_scan.py` fix** (found while running check B2):
  - The scanner took **every** string of **every** `private/*.json` as an identity value, including Reader texts
    (`*.reader.json`) and the pipeline results kept in `private/my_test/` (`result.json`).
  - Generic strings from those results ("r2: must-have MISSING", explanation sentences, flags) caused 14 of the 15
    "unexplained" values.
  - The scanner now reads only identity-store files (written by `/profile`: `name`, `emails`, `phones`, `urls`,
    `addresses`, `personal`).
- **Option (b):** `tasks/T14_final_polish.md` line 38 and `tasks/T14_report.md` line 131 now say "personal repo
  (removed)". No other file outside `private/` contains the handle (search over the repo, `private/` excluded).
- **Commit on `v3-final`:** "T16 demo page, T17 RAG explanation, README/pyarrow clean-up", then
  `git push origin v3-final`.
  - Contents: the T16 demo page (`ui/index.html`, `services/ui.py`, `tests/test_ui.py`, `docs/ui/`, T16 results), the
    T17 RAG explanation, the A1/A2 clean-ups, the scanner fix, the T15–T18 task files and reports.
  - **Left out on purpose (T19):** `services/recruiter.py`, `ui/recruiter.html`, `tests/test_recruiter.py`, the
    recruiter demo CVs and docs, and the 2-line router include in `services/ui.py` plus the header link in
    `ui/index.html` and the "Recruiter flow" paragraphs in `INSTALL.md` / `demo/README.md`. Those files were staged
    in their T16 form, so `v3-final` has a working T16 page without the recruiter flow.

## 2. Evidence (checks)
| check | result |
|---|---|
| B1 `pytest -q` (full working tree, before the split) | **522 passed, 1 skipped** |
| B1 again, on the exact staged tree (`git checkout-index` into a scratch folder) | **519 passed, 4 skipped** (the 3 extra skips need git-ignored data that the scratch copy does not have) |
| B2 first run (`eval/results/2026-10-19_secret_scan_t18/scan.json`) | `.env` values 0, key patterns 0, identity **1 unexplained** → FAIL, task stopped |
| B2 after option (b) (`eval/results/2026-10-19_secret_scan_push/scan.json`, 3,610 files) | `.env` values **0**, key patterns **0**, identity unexplained **0** (23 found, all explained: 12 public dataset text, 9 synthetic test identity, 2 reviewed hashes) → **PASS** |
| B3 `git check-ignore` | `.env`, `private/`, `eval/outbox/`, `models/`, `tools/`, `.n8n/` ignored; 0 staged files under those paths → **PASS** |
| B4 `docs/ui/` | 3 PNG from the demo samples + `result_invite.json`, `result_reject.json`; identity hits in `docs/ui/` and `ui/`: **0** → **PASS** |

Line endings: the staged blobs are LF like the rest of the repo (0 CR bytes checked in the 4 hand-staged files).
Push result: see `tasks/T19_report.md` §2 (git), written after the push.

## 3. Not done / problems
- The handle stays in the history of `b7d1d1a` (`tasks/T14_final_polish.md`). Removing it would need a history
  rewrite and a force-push; the Approver chose not to.
- The remote URL of `origin` in the local `.git/config` is not a committed file and was not changed.

## 4. Questions for the Brain / Approver
1. Keep the scanner fix (identity-store files only)? It removes false hits from pipeline results stored in `private/`.

## 5. Suggested next step
T19's branch `v3-recruiter-flow` from this `v3-final` (done in the same session, see `tasks/T19_report.md`).
