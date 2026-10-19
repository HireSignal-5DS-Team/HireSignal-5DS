# T11: real n8n e2e runs with the Bias Auditor node (real-GPU)

- Workflow: `n8n/hiresignal_v1.json` (32 nodes): ... Aggregate -> **Bias Auditor** (`POST /bias`) -> Outcome input ->
  HTTP /outcome -> Result (with a `bias` block).
- Command: `.venv\Scripts\python scripts\n8n_e2e.py --out eval\results\2026-10-18_n8n_e2e_bias --runs P06,P02 --cards`
- Stack: llama-server :8090, station API :8010 (BIAS_SWAP on, default), n8n 2.43.7 :5678.

| run | execution | outcome | would-be outcome | leakage flags | live swap | Matcher input identical | Bias Auditor node |
|---|---|---|---|---|---|---|---|
| P06 (J1, Djinni CV with a section heading) | 32 | reject | reject | 1 placeholder-only line removed | ran: name replaced (counterfactual female Arab) | yes: no LLM call | 243 ms |
| P02 (J1) | 33 | reject | reject | 1 placeholder-only line removed | ran: name + pronouns added (female Arab) | yes: no LLM call | 69 ms |

- Both: HTTP 200, valid JSON, identity values found in the execution data 0 (0/7 and 0/1), raw CV text in execution
  data: no, all /match with LoRA scale 1.
- Note P06: the "name" the anonymiser stored is the tech phrase it over-masks (pre-existing header-rule issue,
  docs/BIAS_REPORT.md section 2); the swap replaced that phrase, so both texts mask it to [NAME].
- Re-run path, measured once on the live API (`swap_rerun_latency.json`): P45's base CV (over-masked "Qlik Sense")
  with the production decisions; the counterfactual adds a name, which changes the Matcher input -> 5 must-haves
  re-run (/match + Judge): 15.7 s, no decision changed, no review reason. The temporary private file was deleted.
