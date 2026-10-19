# T16 report — demo front-end: one local page that shows the agents working

## In plain words
- **There is now one page, http://127.0.0.1:8010/ui/, that runs a CV + job through the real n8n workflow and shows
  each agent working live.**
  - Reader → Profile ‖ Job → RAG → Matcher "r4 / 8" → Judge → Bias Auditor → Outcome gate → Report Writer → Outcome.
  - Then it shows the decision with its evidence: one card per requirement with the CV quotes, the Matcher's
    confidence, the Judge's verdict and the reasons in plain words.
- **It works offline and is a view only.** No pipeline, prompt, model, gate or n8n change. The secret webhook token is
  added by the server and never reaches the browser (tested).
- **The two demo samples and the personal test CV give the same results as before.** "Open a saved result" replays a
  result.json without running (for a slow laptop during the presentation).
- **One environment problem.** Windows Smart App Control started blocking a pyarrow file today, which stopped the API
  from starting. I removed pyarrow from the project's `.venv` only: nothing at run time needs it. The details and how
  to undo it are below.

## 1. Done (files)
- **`services/ui.py` (new)**:
  - the progress middleware;
  - `POST /ui/run`, `GET /ui/progress`, `GET /ui/last-result`;
  - static mounts `/ui/` (the page) and `/demo/` (the public demo samples, for the "Load sample" buttons).
  - It uses `httpx`, which is already in `requirements.txt`; no new dependency.
- **`services/api.py`**: only 3 lines at the end (`install(app)`), after all station routes, so the existing routes and
  contracts keep priority and stay unchanged.
- **`ui/index.html` (new)**: one file (HTML + CSS + JS), no build, no CDN, no fonts; navy `#14213D` / off-white
  `#F6F5F1` / blue `#2E63C9`.
  - **Input**: CV, job text or .txt, optional card; Run; Open a saved result; Load invite / reject sample.
  - **Timeline**: each box shows its state (waiting / running with a pulse / done / skipped / error), seconds, a
    one-line summary and one sentence on what the agent does. Profile and Job sit side by side. The Matcher, RAG and
    Judge boxes have an "r / total" counter and a bar. The Job Agent shows "skipped: the recruiter's card is used" when
    a card is given.
  - **Result**:
    - the banner (outcome, decided by, score, Met / Missing / Uncertain);
    - requirement cards with filters, quotes, a confidence bar and the Judge verdict;
    - "Model said X → changed to Y by the confidence / quote check";
    - "the Judge's doubt is only listed (gate rule)" on MET cards with a Judge FAIL;
    - reasons in plain words;
    - the Fairness, Reader and Report panels, the timings bar, Open recruiter form (review cases) and Download
      result.json.
  - URL options for headless screenshots: `?demo=invite|reject&autorun=1`, `?last=1`, `&only=result|reqs`.
- **`tests/test_ui.py` (new, 8 tests)**:
  - the page is served offline and holds no token;
  - the progress shape;
  - the token is forwarded to n8n but is not in the reply, the headers, the progress, the last result or the logs;
  - 409 when busy;
  - clear 422 errors for a missing job or a bad card;
  - the middleware records a stage and the response stays byte-identical;
  - nothing is recorded outside a UI run;
  - the summaries carry no CV text.
- **`scripts/start_all.ps1`**: prints `Demo page: http://127.0.0.1:8010/ui/` at the end.
- **Docs**: "Demo page" sections in `demo/README.md` and `INSTALL.md` (§10).
- **Screenshots and replay files** (demo samples only, `docs/ui/`):
  - `1_timeline_running.png`: the reject sample, live, Matcher at 4 / 8;
  - `2_result_top.png`: the invite sample result;
  - `3_requirement_cards.png`;
  - `result_invite.json`, `result_reject.json`.
- **Check results:** `eval/results/2026-10-19_ui_checks/webhook_direct/`.

## 2. Evidence (checks)
1. **Existing tests + webhook unchanged.**
   - `pytest -q` → **522 passed, 1 skipped** (with the 8 new ones).
   - Direct webhook (no page), recruiter cards, as in the demo README (`scripts/n8n_e2e.py --runs P50,P02 --cards`):
     - **P50 invite, score 94** (execution 77);
     - **P02 reject, score 13** (execution 79).

     These are the same outcomes and scores as the T12/T13 runs (`2026-10-19_n8n_e2e_report/`: P50 invite 94; P02
     reject 13 in T13 `final_eval`).
2. **New tests:** see above, all pass. Also checked on the real files: the token value is in none of 28 files (all
   `tools/*.log` and `*.err`, the page, `services/ui.py`, `docs/ui/*`, the private results, the check results). It is
   not returned by `/ui/`, `/ui/progress` or `/ui/last-result`. The check printed counts only.
3. **The page end to end.** Headless Chrome opened the page with `?demo=…&autorun=1`, so the page's own Load-sample and
   Run code ran, not a curl call:
   - **invite → execution 81: invite, 94, 6 requirements**;
   - **reject → execution 83: reject, 13, 8 requirements**.

   During the reject run a second headless Chrome opened the page, which attached to the running run. Screenshot 1
   shows Reader / Profile done, Job skipped (card), RAG and Matcher at 4 / 8, Judge running.
4. **Personal CV** (`private/my_test/yassine_cv.pdf` + `techcarrot_ai_engineer_job.txt`, no card) through `/ui/run`:
   - **reject, score 32, 31 requirements (5 MET / 16 MISSING / 10 UNCERTAIN)**;
   - **31/31 decisions identical** to the earlier `private/my_test/result.json`; only the timings differ (157 s in
     total).
   - Saved only as `private/my_test/result_t16.json`.
5. **Open a saved result** on `private/my_test/result.json`. The file was set in the page's file input through Chrome
   DevTools (Node 24 script, `DOM.setFileInputFiles`). The page rendered:
   - banner "reject", 31 requirement cards;
   - "Replay of result.json (no run)";
   - all 10 timeline boxes rebuilt from the file.

   Screenshot only at `private/my_test/replay_t16.png`.

## 3. Not done / problems
- **Smart App Control blocked pyarrow (environment).**
  - From today, Windows (Smart App Control on, `VerifiedAndReputablePolicyState=1`) refuses to load the unsigned
    `pyarrow/_compute.cp312-win_amd64.pyd`: "Une stratégie de contrôle d'application a bloqué ce fichier".
  - `pytesseract` imports `pandas`, which imports pyarrow when it is installed, so the station API and most tests could
    not even import.
  - I did not change any system setting. I ran `pip uninstall pyarrow` in the project `.venv` only.
  - Nothing in `services/` needs pyarrow. Only the old data-prep scripts (`scripts/djinni_stats.py`, Djinni parquet)
    do.
  - To undo: `.venv\Scripts\python -m pip install pyarrow==26.0.0`. `requirements.txt` still lists it; see question 1.
- **Progress with two runs at once.** `/ui/progress` records every station call while a UI run is active. If someone
  sends a run straight to the webhook at the same time, its calls mix into the timeline.
  - This happened once: execution 78 was a direct webhook run on the personal CV, started at 10:22, during my first
    page run.
  - `/ui/run` itself is limited to one at a time (409).
- **The Report Writer and n8n overhead are not in the timings bar**, because the n8n reply has no time for them. The
  bar shows Reader / Profile / Job / Match+Judge, as in `timings_s`.
- **Screenshots come from headless Chrome** at 1400 px wide. The file-picker buttons show the French Windows label
  ("Choisir un fichier"), because they come from the system locale.
- **Time spent:** about 2 h 20 min. It went past the 2 h time box (still under the 2.5 h stop rule) because of the
  pyarrow block and the screenshot automation.

## Known limits seen in the UI (kept as documented limits, per the Approver)
- **Job Agent "or similar" splitting.** Without a card, "Hands-on experience with probabilistic programming (Pyro,
  PyMC3, JAGS, or similar)" becomes 3 requirements, one per tool (seen in T15's P02 run without a card). The page
  shows them as 3 cards.
- **The Matcher quote issue found on 2026-10-19:** visible in the cards, where a MET's quote does not fully show the
  requirement and the Judge says FAIL. On the invite sample, r3 / r4 / r5 have a Judge FAIL; the gate only lists them
  (the page says so). Not fixed, as decided.

## 4. Questions for the Brain
1. Should `pyarrow` stay in `requirements.txt`? A grader's Windows machine with Smart App Control could hit the same
   block. Only the data-prep scripts use it. Options:
   - move it to an optional "data prep" list;
   - or keep it and add an INSTALL note.
2. Should "A run is already in progress" also cover direct webhook runs? That would need a check in n8n, which is out
   of scope for a view-only task.

## 5. Suggested next step
Record the demo video with the page: the reject sample live (about 70 s), then the invite result, then a replay. Use
`docs/ui/*.png` in the slides.

(No git commands were run in this task.)
