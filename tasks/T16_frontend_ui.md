# T16 — Demo front-end: one local page that shows the agents working

Approver: Yassine (2026-10-19). Time box: **about 2 hours**. If you reach 2.5 h, stop, write what is done in the report.

## Why
Today the only views are the raw JSON reply and the n8n Executions screen. For the presentation and the demo video we need
one clear page where a jury can upload a CV + job and **watch each agent work, step by step**, then read the decision
with its evidence. This is a view only: **no change to the pipeline logic, prompts, models, gate settings or the n8n
workflow.** The architecture is locked (CLAUDE.md).

## What to build

### A. Station API additions (`services/api.py`, small, additive)
1. **Serve the page**: mount a new folder `ui/` (repo root) as static files at `http://127.0.0.1:8010/ui/`.
   One file `ui/index.html` (HTML + CSS + JS inside, no build step, no CDN, no internet; must work offline).
2. **`POST /ui/run`** (multipart: `cv` file, `job_text` text or file, optional `requirements` JSON file).
   The station forwards it to the n8n webhook `http://127.0.0.1:5678/webhook/hiresignal`, adding the header
   `X-HireSignal-Token` **read on the server from `.env`**. Returns the n8n reply unchanged.
   - The token must **never** reach the browser, the page source, a log or a file. Add a test that checks this.
   - Use a library that is already installed (check `requirements.txt`). Do not add new dependencies unless unavoidable;
     if you must, say so in the report.
   - One run at a time: if a run is in progress, answer `409` with "A run is already in progress".
3. **Live progress, `GET /ui/progress`**: a light middleware that records, for the current run, each call to the
   existing station endpoints (`/reader`, `/profile`, `/job`, `/rag/search`, `/match`, `/judge`, `/bias`, `/outcome`,
   `/report`): stage name, start time, end time, status (running / done / error) and a one-line summary taken from the
   response (e.g. Reader: "text PDF, route text"; Job: "31 requirements"; Match: "r7 of 31"; Outcome: "reject").
   In-memory only, reset at the start of each `/ui/run`. **Do not change the request/response contracts of the existing
   endpoints** (n8n must keep working exactly as before). No CV text in the progress events (only counts and labels).

### B. The page (`ui/index.html`)
Keep the project deck style: navy `#14213D`, off-white `#F6F5F1`, blue accent `#2E63C9`; system fonts are fine
(no font downloads). Simple English labels. Three zones:

1. **Input**: CV file (PDF, image, DOCX as supported), job text (paste box or .txt file), optional requirements card
   (.json). Buttons: **Run**, and **Open a saved result** (load a `result.json` from disk and show it without running,
   so the demo still works if the laptop is slow). Two "Load demo sample" shortcuts for the files in `demo/`
   (invite P50 + J4, reject P02 + J1) if easy; skip if it costs more than 15 min.
2. **Agent timeline** (the main point): the locked chain drawn left to right / top to bottom:
   Reader → Profile Agent ‖ Job Agent (side by side, they run in parallel) → RAG lookup → Matcher → Judge →
   Bias Auditor → Outcome gate → Report Writer → Outcome (+ recruiter form if review).
   Each box: state (waiting / running with a pulse / done / skipped / error), elapsed seconds, the one-line summary,
   and a one-sentence "what this agent does" in plain words (take wording from `docs/` / the team guide).
   The page polls `/ui/progress` every 1 s while running. Matcher shows a counter "r7 / 31".
3. **Result**:
   - Outcome banner (invite / reject / review), who decided (gate or recruiter), score, counts Met / Missing / Uncertain.
   - One card per requirement: text, must/nice, final decision, the CV quote(s), a confidence bar (MET/MISSING/UNCERTAIN),
     the Judge verdict, and the review reasons translated to plain words (e.g. `evidence_not_in_cv` →
     "the model gave no exact quote from the CV"; `match:low_confidence` → "the Matcher was unsure").
     When `decision` differs from `model_decision`, show both ("Model said MET → changed to UNCERTAIN by the quote check").
     Filter buttons: All / Met / Missing / Uncertain.
   - Fairness panel: placeholder lines removed, swap test ran (which counterfactual), "identical Matcher input: yes/no",
     would-be outcome.
   - Reader panel: file type, route (text / OCR / vision / late fusion), OCR confidence if any.
   - Report: recruiter summary, candidate letter, source (AI or template fallback), flags for the recruiter.
   - If `review_form_url` is set: a button "Open recruiter form".
   - Timings bar (Reader / Profile / Job / Match+Judge).
   - "Download result.json" button.

### C. Start script and docs
- `scripts/start_all.ps1` prints one more line at the end: `Demo page: http://127.0.0.1:8010/ui/`.
- Add a short "Demo page" section to `demo/README.md` and `INSTALL.md` (how to open it, the Replay button).

## Checks (write results in the report)
1. Existing tests still pass (`pytest`), and the n8n webhook called with curl (demo README command) gives the same
   outcome as before for the invite and reject samples.
2. New tests: `/ui/progress` shape; token never appears in `/ui/run` reply, page source, progress or logs; 409 when busy.
3. Run the page end to end with the **invite** and **reject** demo samples. Save 3 screenshots (timeline while running,
   result top, requirement cards) to `docs/ui/` for the slides. Use only demo samples for these screenshots.
4. Run it once with `private/my_test/yassine_cv.pdf` + `private/my_test/techcarrot_ai_engineer_job.txt` and save that
   result and any screenshot **only under `private/my_test/`** (personal data, git-ignored). It should match the earlier
   reply (reject, 31 requirements); small timing differences are fine.
5. Open the page with "Open a saved result" on `private/my_test/result.json` and check it renders.

## Do NOT
- Change the pipeline, prompts, models, gate settings, the n8n workflow, or any locked decision.
- Fix the Job Agent "or similar" splitting or the Matcher quote issue found on 2026-10-19. The Approver decided to keep
  them as documented limits (no time). Just mention them in the report under "Known limits seen in the UI".
- Use the V1/V2 ports (5173, 5174, 8000, 8001, 8081, 8082) or touch V2.
- Put any personal CV data in `demo/`, `docs/` or anywhere outside `private/`.
- Run git commands (no commit, no push) in this task.

## Report
Write `tasks/T16_report.md` (usual format): what was built, files changed, check results, screenshots paths,
time spent, open questions.
