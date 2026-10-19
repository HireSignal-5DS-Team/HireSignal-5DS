# T20 report: UI/UX redesign (frontend only)

Branch `v3-ui-redesign`, created from `v3-recruiter-flow` @ 78e1704 (clean tree). Not pushed: waiting for the Approver's visual approval.

## 1. Done
- `ui/assets/hs.css` (new): one shared design system for both pages: sidebar, top bar, page header, circle stepper, cards, buttons, upload zones, file list, status pills, pipeline rows, alerts, tables, decision badges, responsive rules (sidebar becomes a top bar below 900 px). Offline: no web fonts, no CDN, no images.
- `ui/assets/hs.js` (new): icons (simple stroke paths drawn for this project, no third-party set), the pipeline renderer, `replay()` (rebuilds stage states from a saved result using only `timings_s`), `merge()` (prefers durations measured live), drag-and-drop, and the backend chip from `GET /ready`.
- `ui/recruiter.html`, same IDs, endpoints and validation:
  - Step 1 "New analysis" now has the job offer card and the candidate CVs card side by side (reference 1). The job card takes pasted text, a dropped or chosen .txt, a .json card or the demo job. The CV card accepts drag-and-drop or choose, adds files to the list, lets you remove each file, and checks the format (PDF/DOCX/PNG/JPG/TXT), empty files, the real 10 MB server limit (`services/ui.py MAX_UPLOAD`) and the 3-CV maximum.
  - Step 3 "AI workflow" (reference 2) follows the real n8n order (`n8n/hiresignal_v1.json`): Reader → [Profile ∥ Job Agent] → loop per requirement [RAG → Matcher → Judge] → Bias Auditor → Outcome Gate → Report Writer → Human Review. It has candidate tabs A/B/C, a spinner for running stages, real requirement progress ("k of N"), real elapsed and completed times, failed-stage errors with the HTTP code, and a "Retry analysis" button that re-sends the same files after a failure.
  - Step 4: candidate cards with must/nice counts, the outcome badge, the evidence matrix (✓/✗/?) with clickable cells and quotes, "Needs your eyes", the Invite/Reject/Hold controls, letters, Approve, Reveal identity and mailto. Logic is unchanged. Added: empty state, backdrop on the drawer, and error columns.
- `ui/index.html` (single-CV demo): the same shell and the same pipeline renderer. All its features are kept (demo samples, replay, `?demo`, `?last`, `?only`).
- Small behaviour changes (frontend only):
  1. Loading or extracting a card no longer jumps to step 2 at once. "Continue to requirements" does that, so the recruiter sees both input cards.
  2. The overall bar is `done / total` (the old `+0.5` for the running candidate is removed, because it was not a measurement).
  3. Batch polling survives a lost API connection: it shows an error and retries every 2 s.
  4. **Bug fix:** with a confirmed card, n8n's "Confirmed job card" node reports `elapsed_s: 0`, so `timings_s.job` is `0`, not `null`. The old drawer and replay treated `0` as "Job Agent ran". Now `0` means skipped (a real `/job` call takes about 20 s).

## 2. Evidence
- `pytest tests -q`: **532 passed, 1 skipped** (before and after the final edits). `tests/test_ui.py` + `tests/test_recruiter.py`: 18 passed (offline page, no token, no ranking words).
- Real-GPU end-to-end run through the new UI (Playwright, live stack started with `scripts/start_all.ps1`): demo job J4 + 3 demo CVs, batch `20261019-172506-88bd`, **110 s** total. Results: A invite (3/3 must, 59.1 s), B review (3/3 must, 31.7 s), C reject (0/3 must, 16.5 s). The live view showed Reader/Profile done, Job Agent skipped and RAG "0 of 6" running. Compare, matrix cell, letter preview and drawer were all exercised. Approve was **not** clicked, so nothing was written to `eval/outbox`.
- Browser console: no page errors. One 404, for `/favicon.ico`.
- Validation checked: a 4th CV is refused ("At most 3 CVs"), and `.exe` is refused (unsupported format).
- Not modified: `services/`, `n8n/`, `prompts/`, `models/`, `rag/`, `eval/`, `data/`, tests. `git diff --stat` shows only `ui/index.html`, `ui/recruiter.html` and the new `ui/assets/`.

## 3. Not done / problems
- Not done: the reference's "Candidates", "Reports", "System status" pages and the user profile/plan. They do not exist in the app, so adding them would mean fake navigation.
- Job PDF/DOCX upload is not offered, because the backend does not support it (unchanged; stated on the page).
- No favicon (cosmetic 404).

## 4. Questions for the Brain
- Step 1 now shows CV file names before the start (the Approver asked for it). After the start, everything is A/B/C as in T19. Is this acceptable for the anonymity story, or should step 1 hide names too?

## 5. Suggested next step
Approver reviews the screenshots. Then commit is pushed on `v3-ui-redesign` (no merge).
