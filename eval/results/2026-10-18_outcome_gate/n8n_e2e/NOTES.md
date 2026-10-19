# n8n runs with the Outcome gate (T08, real-GPU; provisional gate settings t_invite 80, pair flags info)

Webhook runs (`scripts/n8n_e2e.py`); requirements come from the Job Agent (not gold), as in production.

| run | n8n execution | outcome | rule | files |
|---|---|---|---|---|
| P35 (J4) | 23 | reject (score 22) | 1 reject: must-have MISSING (r1, r3) | `P35_*`, `outbox_reject_23_gate.json` |
| P44 (J2, expected invite) | 24 | reject (score 57) | 1 reject: r2, r3, r6 MISSING | `P44_*` |
| P50 (J4, expected invite) | 18 | review (score 75) -> **human: approve-invite** | 2 review: r1-r3 MET doubted (judge:disagrees) | `P50_review_*`, `outbox_invite_18_human.json` |

- P50: the execution waited at "Wait for recruiter (form)"; the form was submitted once (POST to `review_form_url`,
  `field-0=approve-invite`, note "T08 test submission by the Developer (not a recruiter decision)"); execution 18 then
  resumed and ended `success`, writing `eval/outbox/invite/18_cv-afa64db6.json` with `decided_by: human`.
- Superseded attempts: execution 15 (the API had been started before `/outcome` existed: 404, error workflow logged it),
  executions 19 and 21 (the reject branch failed: `eval/outbox/reject` did not exist; n8n needs the folder; fixed in
  `start_n8n.ps1`); executions 16, 20, 22 = the error-workflow runs (log lines in `eval/logs/n8n_errors.log`).
- Execution 17 = an earlier P50 run (its script crashed on a renamed result field after the reply) that is still
  **waiting** at the review form; nobody submitted it. It is pruned after 14 days, or can be cancelled in the n8n UI.
- All `/match` calls used LoRA scale 1; no identity value found in the execution data (`*_execution.json`).
