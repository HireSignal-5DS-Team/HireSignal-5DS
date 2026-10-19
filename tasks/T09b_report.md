# T09b report — tau_conf re-check with V6 rows

**In plain words:** we checked whether the confidence threshold should move now that the Matcher uses the V6
knowledge. It should not: no other value from 0.50 to 0.90 does better on dev, so **tau_conf stays 0.72**. Nothing in
the code changed. Part B (re-scoring retrieval with the Approver's checks) is skipped because the Excel is not filled in yet.

## 1. Done
- `scripts/tau_recheck.py` (new):
  - works offline on `eval/results/2026-10-18_rag_matcher/rows_V6.jsonl`; no llama-server, no Matcher or Judge run;
  - sweeps tau 0.50-0.90 in steps of 0.02 with the same rule as `services/matcher/matcher.py`;
  - then applies the T08b gate with the same `report()` code as `scripts/eval_rag_matcher.py`
    (t_invite 85, pair flags info, judge_met_max_conf 0.999).
- Output: `eval/results/2026-10-18_tau_recheck/sweep.csv` and `summary.json`.
- **Chosen on dev: 0.72 (unchanged).** No default, `.env.example` or PROMPT_LIBRARY change was needed.
- Part B: skipped. In `rag/eval/queries_review.xlsx` (sheet "Review"), column H "DECISION" is empty for all 32 rows.

## 2. Evidence (offline, from real-GPU V6 rows)
- **Check that the replay is correct:** at tau 0.72 the recomputed decisions and review reasons equal the saved rows
  for all 364 rows (assert in the script). Dev and test numbers equal the T09 V6 results.
- **The Judge gap and the two bounds.** The task assumed every row has a Judge verdict, but that is not true:
  - 42 rows (23 dev) were turned into UNCERTAIN by tau 0.72 before `/judge` ran, so their verdict is NOT_APPLICABLE;
  - with tau < 0.72 some of them go back to MET/MISSING with no verdict (19 dev rows at tau 0.50);
  - the gate is therefore computed with two bounds: **A** = Judge silent on those rows, **B** = Judge `judge:disagrees`;
  - a new tau would only be adopted if it were better under both bounds;
  - tau ≥ 0.72 is exact.
- **Dev sweep** (from `sweep.csv`; false invites 0 for every tau and both bounds):

  | tau | false rejects A / B | review rate A / B | macro-F1 |
  |---|---|---|---|
  | 0.50 | 7 / 6 | 0.038 / 0.077 | 0.659 |
  | 0.52 | 7 / 6 | 0.038 / 0.077 | 0.653 |
  | 0.54 | 6 / 6 | 0.077 | 0.667 |
  | 0.56 | 6 / 6 | 0.077 | 0.677 (max) |
  | 0.58-0.70 | 6 / 6 | 0.077 | 0.654-0.668 |
  | **0.72** | **6 / 6** | **0.077** | **0.665** |
  | 0.74-0.90 | 6 / 6 | 0.077 | 0.661 -> 0.608 |

  - No tau has strictly fewer false rejects, and 0.72 already meets the 25% review cap.
  - So by the task rule, 0.72 stays. The best macro-F1 is at 0.56 (0.677), but a macro-F1 gain alone is not enough.
- **Test, once, for 0.72:** macro-F1 0.644; F1 MET 0.771 / MISSING 0.870 / UNCERTAIN 0.291; false MET 13;
  UNCERTAIN recall 0.286; gate false invites 0, false rejects 4, review rate 0.154. Both bounds are equal, since no row
  has an unknown Judge verdict at 0.72.

## 3. Not done / problems
- Part B was not run: the Approver's Excel has no decisions yet. Retrieval numbers still use the Developer-drafted golds.
- The rule uses `confidence.normalized`, the probability renormalised over the 3 labels, as the code does. The task
  text says `label_prob`. They differ by up to 0.029 (70 of 364 rows by more than 0.001). At 0.72 they give the same flips on all rows.
  Over the whole sweep, 10 (row, tau) threshold outcomes would differ. I did not sweep `label_prob` separately, because production uses
  `normalized`.
- Below 0.72 the result rests on the two bounds, not on real Judge verdicts. It does not matter for the choice:
  neither bound beats 0.72.

## 4. Questions for the Brain
- None. Part B will run when the Excel has a DECISION for all 32 rows.

## 5. Suggested next step
Fill in `rag/eval/queries_review.xlsx` (column H, and column I for CHANGE), then run T09b Part B.

---

## Part B result (run in T10 Part 0, 2026-10-18)

**In plain words:** the Approver's checks were applied (22 OK, 10 CHANGE, 0 DROP). With the checked answers, every
score goes up, but dense MiniLM is **no longer first on dev**: bge-small-en-v1.5 is slightly ahead, by 3 of 24 queries.
On test MiniLM stays ahead. T10 says to stop in this case, so T10 has not started yet.

### Done
- `scripts/apply_query_review.py` (new) reads the Review sheet and writes `rag/eval/queries.jsonl`.
  - The pre-review file is kept as `rag/eval/queries_drafted.jsonl`.
  - `how_made` of the 32 rows gets "; checked by the Approver 2026-10-18".
  - The 10 CHANGE golds come from column I. All labels match an exact ESCO label, and none is duplicated in ESCO.
  - 46 queries remain (dev 24 / test 22).
- `rag/rescore.py` (new) re-scores the 13 configurations of the RAG_REPORT section-4 table, which include the 9 rows
  of the T09 report table and the chosen one. Same scoring as `rag/evaluate.py`. Results are in
  `eval/results/2026-10-18_rag_retrieval_checked/summary.json` (real-GPU).
- `rag/RAG_REPORT.md`: section 3 now says "checked by the Approver"; section 4 has the new table and readings;
  section 6 notes both MRR versions.

### Evidence (checked golds)

| configuration | dev hit@1 | dev hit@3 | dev MRR@10 | test MRR@10 | dev MRR@10 on drafted golds (T09) |
|---|---|---|---|---|---|
| BM25 A (V0) | 0.417 | 0.583 | 0.520 | 0.425 | 0.436 |
| **dense bge-small-en-v1.5** (first on dev) | 0.792 | 0.833 | **0.824** | 0.609 | 0.751 |
| dense all-MiniLM-L6-v2 (production, V6) | 0.750 | 0.833 | 0.798 | **0.712** | 0.762 |
| dense multilingual-e5-base | 0.625 | 0.833 | 0.723 | 0.556 | 0.686 |
| hybrid MiniLM (RRF) | 0.583 | 0.792 | 0.686 | 0.684 | 0.592 |
| dense MiniLM + ms-marco rerank | 0.708 | 0.833 | 0.765 | 0.632 | 0.689 |

The full 13-row table is in RAG_REPORT section 4.

**Where the dev gap comes from** (rank of the first gold concept, MiniLM vs bge-small):
- O03 "AWS RDS, AWS Aurora Postgres": 8 vs 3;
- O22 "Docker": 3 vs 1;
- O24 "asynchronous programming": 2 vs 4.

Same hit@3 (0.833). On test, bge-small loses on 7 of the 10 queries where the two differ.

### Not done / problems
- Only the table's 13 configurations were re-run, not the full 84-configuration grid, as the task says. A config
  outside the table could now rank higher on dev.
- Production was not changed: it still uses MiniLM (V6). V6 was chosen in T09 on the Matcher effect with MiniLM;
  bge-small was never run through the Matcher.

### Question for the Brain (T10 is waiting on this)
- By the retrieval rule (dev MRR@10), bge-small-en-v1.5 now wins: 0.824 vs 0.798, a gap of 3 of 24 queries.
  Options:
  - **(a)** keep MiniLM in production. The gap is small, test favours MiniLM, and V6 was chosen on the Matcher
    effect, which was measured with MiniLM.
  - **(b)** switch V6 to bge-small. That would need a Matcher re-run (V6 with bge, about 20 min on GPU, 364 rows) to
    check the T09 Part D result still holds.
- My suggestion: (a), and report bge-small as the dev winner on retrieval only.

**Answer (Approver, 2026-10-18): option (a).** The dev gap is 3 of 24 queries with equal hit@3, so it counts as a tie;
the tie-break is the simpler, faster model, all-MiniLM-L6-v2. Written in RAG_REPORT section 4; the test result is only
reported, not used as the reason.
