# T12: real n8n e2e runs with the Report Writer node (real-GPU, prompt report_writer v2)

- Workflow `n8n/hiresignal_v1.json` (33 nodes): ... HTTP /outcome -> **Report Writer** (`POST /report`) -> Result ->
  Respond to Webhook -> Switch outcome -> Decided by gate / Wait for recruiter (form) -> Outbox letter.
- Command: `.venv\Scripts\python scripts\n8n_e2e.py --out eval\results\2026-10-19_n8n_e2e_report --runs P50,P02,P15 --cards`

| run | execution | outcome | report source | Report Writer node | letter |
|---|---|---|---|---|---|
| P50 (J4) | 37 | invite (score 94) | LLM, first try | 9.8 s | outbox `eval/outbox/invite/37_*.json`: letter = the checked report letter |
| P02 (J1) | 38 | reject (score 13) | LLM, first try | 9.8 s | outbox `eval/outbox/reject/38_*.json`: letter = the checked report letter |
| P15 (J2) | 39 | review (score 50), waiting at the recruiter form | LLM, first try | 9.0 s | none (review); the form description shows the summary, the lines and the flags |

- All: HTTP 200, identity found 0, LoRA scale 1 on the Matcher calls.
- `../2026-10-19_n8n_e2e_report_v1prompt/`: a first run (executions 34-36) made while the code default of
  `REPORT_PROMPT` was still v1 (fixed): P50 and P15 passed on the first try, P02 fell back to the template ("reject
  letter does not name missing must-have r5").
