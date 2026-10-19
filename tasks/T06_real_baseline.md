# T06 — Anonymiser fix + evaluation on real labelled CVs (baseline)

Read `CLAUDE.md` first. Answers to your T05 questions: 1) yes, fix it here (Part 0). 2) yes, prune n8n executions after 14 days (Part 0). 3) yes, `N8N_USE_WORKFLOW_PUBLICATION_SERVICE=false` is accepted; document it as a known n8n 2.43 + SQLite workaround. 4) for evaluation, give the Matcher the labelers' requirement list (Part A); the Job Agent is evaluated separately.

**Gold labels are ready** (built by the Brain, do not edit): `data/labels/gold/requirements_gold.csv` (280 rows: `gold_decision`, `gold_quote`, `split` dev/test, `source`), `pairs_gold.csv` (outcomes: NOT yet human-checked, treat as provisional), `summary.json`, `build_gold.py`. Method: AI pre-labels (Claude) checked row by row by a teammate; 10/280 rows changed (3.6%). Use `gold_decision` only; some human quotes are not exact substrings (flagged in summary.json), do not use gold quotes for scoring.

## Part 0 — Two fixes
1. **Anonymiser false positive** ("BI Tools" taken as the name, so "Power BI" became "Power [NAME]"): skip header-name detection when the CV has no section headings, and add common tech/CV words to the not-a-name list. Measure before/after on: the 40 real CVs (count `[NAME]` replacements and how many replaced words are obviously not names), and V2's 10 synthetic CVs with gold identity (`eval/profile_agent/` in V2: copy them in with the rule-6 header) for identity leaks (must stay 0). Add tests.
2. n8n pruning in `scripts/start_n8n.ps1` (process env only): `EXECUTIONS_DATA_PRUNE=true`, `EXECUTIONS_DATA_MAX_AGE=336` (hours).

## Part A — Real-data evaluation harness (`scripts/eval_real.py`), results in `eval/results/<date>_real_baseline/`
Call the station API directly (same code as the n8n nodes; faster for batch runs). For each of the 40 pairs:
1. `/reader` → `/profile` on the CV file (the anonymised text is what the Matcher sees in production).
2. `/match` for each gold requirement of that pair, built from `requirements_gold.csv` (requirement text, kind, category, min_years). Not from the Job Agent.
3. **Also save the model's confidence** for the decision, so T07 can use it without re-running: ask llama-server for token log-probabilities (check what b11139 supports: `logprobs`/`top_logprobs` in chat completions or `n_probs`; cite it) and store the probability of the chosen decision label and of the other two labels. If it cannot be done with constrained decoding, say so and store nothing.

**Metrics** (report dev, test and all 40 separately): accuracy, macro-F1, per-class F1, confusion matrix, false-MET count/rate, share of MET with a verified quote, mean latency. Then the **TEMP outcome rule** (from T05) on the Matcher output vs `pairs_gold.csv` (label it provisional: outcomes not human-checked yet, and there are 0 gold invites).
**Job Agent check:** run `/job` on J1–J4; align its requirements with the 28 gold requirements by source sentence; report how many gold requirements it found, extra ones, and must/nice agreement.
**Error analysis:** `ERRORS.md` listing every Matcher disagreement (pair, requirement, gold vs model, model quote, the CV line that supports gold), grouped as false MET / false MISSING / missed UNCERTAIN / other, with a one-line guess of the cause (anonymiser damage, wrong quote, no knowledge needed, etc.).
Label everything real-GPU. Do not tune anything on the test split.

## Report
`tasks/T06_report.md`. Stop llama-server and the API at the end; leave n8n as it is.
