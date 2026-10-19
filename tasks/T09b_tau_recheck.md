# T09b — Quick re-check of tau_conf with V6 rows (time-box: 30 min, offline only)

Read `CLAUDE.md` first. Answers to your T09 questions (Approver, 2026-10-18):
1. **Keep V6** as the production setup. No change needed.
2. **Re-check tau_conf, quickly.** Details below. Do not spend long on it.
3. **The Approver checks the 32 drafted query golds himself.** The file is `rag/eval/queries_review.xlsx` (Brain-made). Part B runs only when he has filled it in.

## Part A — tau_conf sweep (now)
- **Offline only.** Use the saved `eval/results/2026-10-18_rag_matcher/rows_V6.jsonl`: it already has `model_decision`, `confidence.label_prob` and `judge` for all 364 rows. Do **not** start llama-server and do not re-run the Matcher or the Judge.
- Recompute the confidence rule (label prob < tau → UNCERTAIN) for tau from 0.50 to 0.90, step 0.02. Then apply the T08b gate (variant b) offline, with the same code as `scripts/eval_rag_matcher.py`.
- **Choose on dev only**, in this order:
  1. 0 false invites (hard rule);
  2. review rate ≤ 25%;
  3. fewest false rejects;
  4. highest requirement macro-F1.
- **Keep 0.72 unless another value is strictly better on step 2 or 3.** A gain in macro-F1 alone is not enough to change it; a tie keeps 0.72.
- Report test **once**, for 0.72 and for the chosen value (if different). Never tune on test.
- If the value changes: update the default in `services/api.py`, `config/.env.example` and the `guard-outcome-gate` / confidence row in `prompts/PROMPT_LIBRARY.md`. Run `pytest -q`.
- Output: `eval/results/2026-10-18_tau_recheck/` (`sweep.csv` + a short `summary.json`).

## Part B — re-score retrieval with the human-checked golds (only when the Excel is filled in)
- Run this only if `rag/eval/queries_review.xlsx` has a DECISION in column H for all 32 rows. Otherwise skip it and say so.
- For each row:
  - **OK** → keep the gold as it is;
  - **CHANGE** → replace `gold_labels` / `gold_uris` with the labels in column I (match the exact ESCO label; report any label that doesn't match);
  - **DROP** → remove the query.
- Write `rag/eval/queries.jsonl`. Set `how_made` to "…; checked by the Approver 2026-10-18".
- Re-run only the configurations in the T09 report's retrieval table plus the chosen one (not the full 84 grid). Check that dense MiniLM is still the best on dev.
- Update the tables in `rag/RAG_REPORT.md` (sections 3–4): replace "not human-verified" with "checked by the Approver".

## Report
Write `tasks/T09b_report.md`, short: the chosen tau and why (one small table, dev + test), plus the Part B result or "skipped". No n8n changes. No git.
