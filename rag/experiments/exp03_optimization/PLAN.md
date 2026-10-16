# Experiment 03 — optimisation of the promising methods (pre-registration)

Committed before any exp03 run. Experiment 02 and its 300 ms rule are unchanged; exp03 defines its own profiles.

## Data splits and their only allowed use

| Split | File | Use |
|---|---|---|
| Development | `rag/eval/queries_reviewed.jsonl` (42) | configuration and parameter choice |
| Calibration | `calibration_queries.jsonl` (template-generated, seed 0) | abstention thresholds only (5-fold CV reported) |
| exp02 holdout | `../exp02_benchmark/holdout_queries.jsonl` | **sealed**: already inspected, not used again |
| Final test | `final_test_queries.jsonl` (hand-written by Claude, sealed by SHA256) | evaluated **only after human review**; only source of generalisation claims |

## Product profiles and budgets (justification)

- **Real-time** — interactive lookups and per-request n8n calls: p95 ≤ 300 ms per query (exp02 limit, unchanged).
- **Async** — the Matcher collects evidence for ~15 requirements of one CV–job pair inside an n8n run whose LLM steps
  already take several seconds each, and the recruiter reviews results later: p95 ≤ 2,000 ms per query on the
  4-core CPU (≤ 30 s retrieval per screening). Extra RAM ≤ 1.5 GB over the baseline, no additional service.

## Selection rule per profile

1. Candidates must meet the profile's latency/RAM budget (repeated-measurement p95, 5 repeats × 20 queries).
2. Among them, take the highest dev Matcher MRR (ESCO + job-filtered, pooled).
3. Adopt it over the baseline only if, on dev, the paired bootstrap 95% CI of the MRR difference excludes 0 or
   exact McNemar p < 0.05 on Hit@1; otherwise keep the baseline for that profile. Ties go to the simpler option.
4. Abstention threshold: chosen on the calibration split to maximise balanced accuracy (answer vs abstain).
5. Generalisation claims only from the final test set after human review.

## Experiments (dev only)

Chunk tuning (e5-small): structure max section {150, 300, 500} words; sliding {100/15, 200/30, 300/45};
parent-child child unit {1 sentence, 3-sentence window stride 2}. Embeddings: e5-base × {structure, parent-child}.
Rerankers {mmarco-mMiniLMv2-L12 (multilingual), ms-marco-MiniLM-L-6 (English), bge-reranker-v2-m3} × top-{5,10,20};
int8 dynamic quantisation of rerankers; combinations of the best chunking, embedding and reranker.
GPU: not available in this environment (reported as blocked, not estimated).
