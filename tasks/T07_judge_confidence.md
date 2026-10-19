# T07 — Judge (NLI) + confidence check, measured against the T06 baseline

Read `CLAUDE.md` first. Start only after T06 is finished and `tasks/T06_report.md` exists. Reuse T06's saved Matcher outputs (`eval/results/2026-10-18_real_baseline/rows.jsonl`): do not re-run the Matcher for the measurements.

Answers to your T06 questions: 1) yes: confidence + Judge go into `review_reasons` (this task); the full Outcome gate is the next task (T08), after gold outcomes are final. 2) no prompt change now: try the confidence rule first (Part B) and measure how many gold-UNCERTAIN rows it recovers; matcher-v2 only if this fails. 3) keep J2 r6 in gold for now; report every metric also WITHOUT J2 r6 as a sensitivity line (the Approver decides later). 4) yes, count a split group as one requirement. Also: the missing `skill_terms` belongs to the RAG task; do not change it here.

Why: T06 shows the LoRA almost never says UNCERTAIN and sometimes says MET with quotes that do not prove the requirement. Two complementary checks: the **confidence check** catches answers the model itself is unsure about; the **Judge** catches confident answers whose quote does not support them.

## Part A — Judge station (`POST /judge`, station 6)
- Model: `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` from `models/` (Decision 18). Reuse V2 `matcher/judge.py` logic (rule-6 header): premise = verified quotes widened to their CV line; MISSING/not_documented = whole CV in chunks; UNCERTAIN = not applicable; labels mapped by name; NLI never sees RAG knowledge.
- Input: anonymised CV text + requirement + the Matcher result. Output: verdict PASS / FAIL / UNCERTAIN / NOT_APPLICABLE, scores, and review reasons `judge:disagrees` / `judge:uncertain`. It never changes the Matcher decision.
- Thresholds (`tau_pass`, `tau_fail`) chosen on the **dev** split only.
- To judge T06 rows you need the exact anonymised text the Matcher saw: regenerate it with the same anonymiser code (rules only) and check that every saved quote span still matches; report mismatches.

## Part B — Confidence check (inside `/match`)
- Use the saved probability of the chosen label (T06 `confidence.normalized`). If it is below `tau_conf`, the station returns decision UNCERTAIN, keeps `model_decision`, and adds review reason `match:low_confidence`.
- Choose `tau_conf` on **dev** only. Show the trade-off table for several thresholds (e.g. 0.80, 0.85, 0.90, 0.95, 0.98): errors caught vs correct answers sent to review. Pick the value that maximises dev macro-F1 and say why.
- Also report the same rule on bench-v1 val (202, synthetic) as a secondary check, if T03 saved probabilities; otherwise skip.

## Part C — Ablation on the 40 real pairs
Report on **test** (and dev for reference), from the saved rows: (1) baseline T06, (2) + confidence, (3) + Judge, (4) + both. Metrics: accuracy, macro-F1, per-class F1, false-MET, UNCERTAIN recall, and **review load** (share of requirements flagged for review). Plus the TEMP outcome rule on each variant vs `pairs_gold.csv` (provisional). Results in `eval/results/<date>_judge_confidence/` with a short `SUMMARY.md` that a non-expert can read (what each check catches, with 2 real examples each).

## Part D — Wire into n8n
Add an HTTP `/judge` node after `/match` inside the requirement loop; pass review reasons through; re-export and clean `n8n/hiresignal_v1.json`; one real end-to-end webhook run to show it works.

## Rules
Tests for the new code (mock models where needed). Log the confidence rule and Judge thresholds in `prompts/PROMPT_LIBRARY.md` as guardrails with before/after numbers. Real-GPU/real-CPU labels on every number. Never tune on test.

## Report
`tasks/T07_report.md`. Stop llama-server and the API at the end.
