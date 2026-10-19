# T12: real n8n e2e runs with the Report Writer node (real-GPU)

- Workflow `n8n/hiresignal_v1.json` (33 nodes): ... HTTP /outcome -> **Report Writer** (`POST /report`) -> Result ->
  Respond to Webhook -> Switch outcome -> Decided by gate / Wait for recruiter (form) -> Outbox letter.
- Command: `.venv\Scripts\python scripts\n8n_e2e.py --out eval\results\2026-10-19_n8n_e2e_report --runs P50,P02,P15 --cards`

| run | execution | outcome | report source | Report Writer node | letter |
|---|---|---|---|---|---|
| P50 (J4) | 34 | invite (score 94) | llm, first try | 9.2 s | invitation; outbox `eval/outbox/invite/34_*.json` letter = the checked report letter |
| P02 (J1) | 35 | reject (score 13) | template (`report:template_fallback`): first try and retry both failed "reject letter does not name missing must-have r5" (the model wrote "cloud" without "Amazon SageMaker") | 17.5 s | template reject letter with the missing must-haves + the right to a human review; outbox `eval/outbox/reject/35_*.json` |
| P15 (J2) | 36 | review (score 50), waiting at the recruiter form | llm, first try | 8.4 s | none (review); the form description shows the summary, the requirement lines and the flags |

- All: HTTP 200, identity found 0 (0/0, 0/1, 0/0), LoRA scale 1 on the Matcher calls.
