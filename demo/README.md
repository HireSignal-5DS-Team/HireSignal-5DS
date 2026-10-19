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

## Where to look

- **n8n editor**: http://localhost:5678 → Executions. Every station is a node: Reader → Profile → Job card → RAG lookup
  → Match → Judge → Bias Auditor → Outcome → Report Writer → Switch.
- **Review case**: the reply's `review_form_url` opens the recruiter form, which shows the summary, the requirement
  lines and the flags. The recruiter's decision gets a generated, fact-checked letter in `eval/outbox/<decision>/`.
- **A request without the token header** gets HTTP 403.
