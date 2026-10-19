# HireSignal demo pack (T13)

Three inputs, one per outcome type. Each one sends a CV file, the job text and the recruiter-confirmed requirement
card to the n8n webhook.

| case | CV | job | expected outcome (measured, T12/T13 e2e) |
|---|---|---|---|
| invite | `invite_P50_cv.pdf` (text PDF made from the Djinni CV of pair P50) | J4 Python BackEnd Developer | **invite**: invitation letter in `eval/outbox/invite/` |
| reject | `reject_P02_cv.pdf` (L01, Djinni CV of pair P02) | J1 Data Scientist | **reject**: letter with the missing must-haves + the right to a human review in `eval/outbox/reject/` |
| phone photo | `photo_P15_cv.jpg` (phone photo of a laptop screen showing L02 = pair P15) | J2 Data Engineer | **review**: Reader `late` fusion (OCR + qwen2.5vl), then the recruiter form; a human decision writes a checked letter |

The CVs come from the public Djinni dataset (see `data/processed/NOTICE_DJINNI.md`). They are already anonymised: no
names.

## Run

1. Start everything: `powershell -ExecutionPolicy Bypass -File scripts\start_all.ps1` (see `INSTALL.md`).
2. Send a case, in PowerShell from the repo root. The token is read from `.env` and never printed:

```powershell
$tok = (Select-String -Path .env -Pattern '^WEBHOOK_TOKEN=(.+)$').Matches[0].Groups[1].Value
# invite
curl.exe -s -X POST http://127.0.0.1:5678/webhook/hiresignal -H "X-HireSignal-Token: $tok" `
  -F "cv=@demo/invite_P50_cv.pdf" -F "job_text=<demo/invite_P50_job_J4.txt" -F "requirements=<demo/invite_P50_requirements_J4.json"
# reject
curl.exe -s -X POST http://127.0.0.1:5678/webhook/hiresignal -H "X-HireSignal-Token: $tok" `
  -F "cv=@demo/reject_P02_cv.pdf" -F "job_text=<demo/reject_P02_job_J1.txt" -F "requirements=<demo/reject_P02_requirements_J1.json"
# phone photo (takes ~3-4 min in the full chain: OCR + vision model; FINAL_EVAL §2)
curl.exe -s -X POST http://127.0.0.1:5678/webhook/hiresignal -H "X-HireSignal-Token: $tok" `
  -F "cv=@demo/photo_P15_cv.jpg" -F "job_text=<demo/photo_P15_job_J2.txt" -F "requirements=<demo/photo_P15_requirements_J2.json"
```

Or run all three and check the identity scan:
`.venv\Scripts\python scripts\n8n_e2e.py --out eval\results\<date>_demo --runs P50,P02,scan:K01_photo.jpg:P15 --cards`

The reply is the `Result` JSON: `outcome`, `score`, `rule`, `reasons`, the per-requirement decisions with verified
quotes, and three blocks:
- `reader` (mode, route per page);
- `bias` (flags, swap test);
- `report` (recruiter summary, requirement lines, candidate letter, flags).

## Demo page (T16)

Open **http://127.0.0.1:8010/ui/** (served by the station API, works offline). It is a view only: the run still goes
through the same n8n workflow.

1. **Input.**
   - Choose a CV file and paste the job text (or choose a .txt file).
   - Optionally choose a confirmed requirement card (.json); then the Job Agent is skipped.
   - Or press **Load invite sample** / **Load reject sample**, which load the files of this folder.
2. **Run.** The station API forwards the upload to the n8n webhook and adds `X-HireSignal-Token` on the server. Only
   one run at a time (a second one gets "A run is already in progress").
3. **Agent timeline.** Every second the page reads `/ui/progress`. Each agent box shows its state (waiting / running /
   done / skipped / error), seconds and a one-line summary. The Matcher shows "r4 / 8".
4. **Result.**
   - Outcome banner, and one card per requirement: quotes, Matcher confidence, Judge verdict, review reasons in plain
     words. Filter by All / Met / Missing / Uncertain.
   - Fairness, Reader and Report panels, timings, **Download result.json**.
   - **Open recruiter form** on review cases.
5. **Replay.** **Open a saved result** loads a `result.json` from disk and shows it without running (use it if the
   laptop is slow during a presentation). `docs/ui/result_invite.json` and `result_reject.json` are ready-made.

Screenshots for the slides: `docs/ui/1_timeline_running.png`, `2_result_top.png`, `3_requirement_cards.png`.
For headless screenshots, the page also accepts:
- `?demo=invite|reject&autorun=1` (load a sample and press Run);
- `?last=1` (re-open the last run of this API session);
- `&only=result|reqs` (hide the zones above).

## Recruiter flow (T19)

Open **http://127.0.0.1:8010/ui/recruiter.html** for one job with up to 3 candidates. The steps:
1. **Job:** press **Load the demo job J4 + its card**.
2. **Requirements:** confirm the card.
3. **Candidates:** press **Load 3 demo CVs for the J4 job**, then **Run** (about 3–4 minutes for 3 text CVs).
4. **Compare & decide:** the evidence matrix, then Invite / Reject / Hold, the letter preview, Approve, and Reveal
   identity.

The two extra CVs, `recruiter_P32_cv.txt` and `recruiter_P35_cv.txt`, are the gold pairs P32 and P35 of job J4 from the
Djinni dataset (MIT, anonymised at source). With P50 they give one invite, one review and one reject. There is no
ranking and no automatic e-mail; `docs/RECRUITER_FLOW.md` explains why.

## Where to look

- **n8n editor**: http://localhost:5678 → Executions. Every station is a node: Reader → Profile → Job card → RAG lookup
  → Match → Judge → Bias Auditor → Outcome → Report Writer → Switch.
- **Review case**: the reply's `review_form_url` opens the recruiter form, which shows the summary, the requirement
  lines and the flags. The recruiter's decision gets a generated, fact-checked letter in `eval/outbox/<decision>/`.
- **A request without the token header** gets HTTP 403.
