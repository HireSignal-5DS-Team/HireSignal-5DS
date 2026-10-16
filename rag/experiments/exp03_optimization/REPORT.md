# Experiment 03 — optimisation of the promising methods (2026-10-14)

Pre-registration: `PLAN.md` (`7ed9824`), audit of exp02: `AUDIT.md`. Splits created and sealed before any run
(`8a766ec`). Raw data: `results/` (per-query CSVs, latency raw/summary, calibration). Selection: `selection.json`,
`results/selection.md`. Hardware: 4-core cloud CPU, no GPU; exact cosine search for every dense model.
Experiment 02 and its selection rule are unchanged.

## What was run

| Group | Configurations | Status |
|---|---|---|
| A chunk tuning (e5-small) | structure max section {150, 300, 500} words; sliding {100/15, 200/30, 300/45}; parent-child children {1 sentence, 3-sentence window stride 2} | tested |
| B embeddings | e5-base × {structure, parent-child} | tested |
| C rerankers | ms-marco-MiniLM-L-6 (English), mmarco-mMiniLMv2-L12 (multilingual), bge-reranker-v2-m3 × top-{5, 10, 20} on structure + e5-small | tested |
| C int8 | dynamic int8 quantisation (PyTorch, CPU) of mmarco and bge at top-10 | tested |
| D combinations | {parent-child + e5-small, parent-child + e5-base, structure + e5-base} × {mmarco, bge} at top-10 | tested |
| GPU acceleration | — | **blocked**: no GPU in this environment; the laptop GPU is reserved for the LLM benchmark. `latency.py` refuses to report GPU numbers it did not measure. |
| Calibrated abstention | thresholds on 13 finalists, 40-query calibration split, 5-fold CV | tested |
| Repeated latency | 13 finalists, 20 queries × 5 repeats (3 for > 1.5 s), warm models, end-to-end (query embedding + search + rerank) | tested |
| Final test set (36 queries, sealed) | — | **pending human review**; not evaluated |

## Results on the development set (42 queries; Matcher = ESCO + job-filtered, n = 40; job-ID filter mandatory)

Columns: ESCO Hit@1 (/16), job-filtered Hit@1 (/24), all-jobs Hit@1 (/24), Matcher Hit@1 (/40), Matcher MRR,
Matcher nDCG@10, all-jobs MRR, all-jobs source attribution@1 (top result from the right posting), paired MRR difference
vs baseline with bootstrap 95% CI and exact McNemar p, latency median / p95 ms (repeated, finalists only; others
single-shot median), indexing s, index MB, model RAM MB (RSS growth, indicative).

| Configuration | ESCO@1 | Job@1 | All-jobs@1 | Matcher@1 | Matcher MRR | nDCG@10 | All-jobs MRR | Attribution@1 | Δ MRR vs baseline | Latency ms | Index s | Index MB | RAM MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `structure@150 + e5-small` | 11 | 16 | 8 | 27 | 0.804 | 0.848 | 0.447 | 0.417 | -0.060 [-0.127, -0.004], p=0.219 | single-shot 111 | 48.3 | 2.85 | 378 |
| `structure@300 + e5-small` | 11 | 20 | 10 | 31 | 0.865 | 0.893 | 0.527 | 0.458 | baseline | 112 / 128 | 50.7 | 2.66 | 378 |
| `structure@500 + e5-small` | 11 | 19 | 11 | 30 | 0.844 | 0.877 | 0.54 | 0.5 | -0.021 [-0.071, +0.025], p=1.0 | single-shot 108 | 46.4 | 2.6 | 378 |
| `sliding@100/15 + e5-small` | 11 | 18 | 9 | 29 | 0.815 | 0.855 | 0.495 | 0.542 | -0.049 [-0.146, +0.044], p=0.754 | single-shot 112 | 49.1 | 3.0 | 378 |
| `sliding@200/30 + e5-small` | 11 | 18 | 9 | 29 | 0.835 | 0.871 | 0.467 | 0.417 | -0.029 [-0.087, +0.025], p=0.625 | single-shot 108 | 49.8 | 2.69 | 378 |
| `sliding@300/45 + e5-small` | 11 | 18 | 8 | 29 | 0.831 | 0.868 | 0.435 | 0.417 | -0.033 [-0.100, +0.029], p=0.688 | single-shot 109 | 49.3 | 2.59 | 378 |
| `pc@1s + e5-small` | 11 | 22 | 10 | 33 | 0.885 | 0.908 | 0.572 | 0.417 | +0.021 [-0.042, +0.087], p=0.688 | 112 / 130 | 54.5 | 4.9 | 378 |
| `pc@3s2 + e5-small` | 11 | 23 | 9 | 34 | 0.902 | 0.921 | 0.542 | 0.417 | +0.037 [-0.013, +0.100], p=0.375 | 115 / 132 | 53.8 | 3.58 | 378 |
| `structure@300 + e5-base` | 11 | 22 | 7 | 33 | 0.897 | 0.923 | 0.437 | 0.333 | +0.033 [-0.036, +0.102], p=0.688 | 135 / 164 | 126.6 | 5.33 | 153 |
| `pc@1s + e5-base` | 11 | 22 | 9 | 33 | 0.897 | 0.923 | 0.542 | 0.375 | +0.033 [-0.042, +0.115], p=0.727 | 136 / 170 | 139.2 | 9.8 | 153 |
| `structure@300 + e5-small > msmarco-l6@5` | 11 | 21 | 14 | 32 | 0.856 | 0.885 | 0.633 | 0.625 | -0.009 [-0.101, +0.080], p=1.0 | single-shot 314 | 50.7 | 2.66 | 453 |
| `structure@300 + e5-small > msmarco-l6@10` | 11 | 21 | 16 | 32 | 0.847 | 0.877 | 0.708 | 0.75 | -0.017 [-0.116, +0.075], p=1.0 | single-shot 463 | 50.7 | 2.66 | 453 |
| `structure@300 + e5-small > msmarco-l6@20` | 11 | 21 | 17 | 32 | 0.848 | 0.873 | 0.734 | 0.792 | -0.017 [-0.119, +0.077], p=1.0 | single-shot 540 | 50.7 | 2.66 | 453 |
| `structure@300 + e5-small > mmarco@5` | 11 | 22 | 13 | 33 | 0.9 | 0.92 | 0.619 | 0.583 | +0.035 [-0.025, +0.098], p=0.688 | 429 / 636 | 50.7 | 2.66 | 517 |
| `structure@300 + e5-small > mmarco@10` | 11 | 22 | 13 | 33 | 0.887 | 0.91 | 0.667 | 0.583 | +0.023 [-0.040, +0.087], p=0.688 | 744 / 1081 | 50.7 | 2.66 | 517 |
| `structure@300 + e5-small > mmarco@20` | 11 | 22 | 13 | 33 | 0.895 | 0.921 | 0.692 | 0.625 | +0.031 [-0.051, +0.120], p=0.727 | 923 / 1309 | 50.7 | 2.66 | 517 |
| `structure@300 + e5-small > bge@5` | 11 | 23 | 12 | 34 | 0.908 | 0.926 | 0.598 | 0.542 | +0.044 [-0.010, +0.102], p=0.375 | 3537 / 5366 | 50.7 | 2.66 | 529 |
| `structure@300 + e5-small > bge@10` | 11 | 23 | 14 | 34 | 0.908 | 0.926 | 0.674 | 0.625 | +0.044 [-0.010, +0.102], p=0.375 | single-shot 9380 | 50.7 | 2.66 | 529 |
| `structure@300 + e5-small > bge@20` | 12 | 23 | 15 | 35 | 0.929 | 0.947 | 0.733 | 0.708 | +0.065 [-0.010, +0.150], p=0.219 | single-shot 10198 | 50.7 | 2.66 | 529 |
| `structure@300 + e5-small > mmarco-int8@10` | 10 | 21 | 14 | 31 | 0.838 | 0.871 | 0.663 | 0.625 | -0.026 [-0.118, +0.060], p=1.0 | single-shot 825 | 50.7 | 2.66 | 582 |
| `structure@300 + e5-small > bge-int8@10` | 11 | 23 | 15 | 34 | 0.912 | 0.929 | 0.701 | 0.667 | +0.048 [-0.006, +0.106], p=0.375 | 3993 / 6084 | 50.7 | 2.66 | 2082 |
| `pc@1s + e5-small > mmarco@10` | 11 | 22 | 14 | 33 | 0.887 | 0.91 | 0.708 | 0.625 | +0.023 [-0.040, +0.087], p=0.688 | 751 / 1050 | 54.5 | 4.9 | 517 |
| `pc@1s + e5-small > bge@10` | 11 | 23 | 15 | 34 | 0.908 | 0.926 | 0.712 | 0.708 | +0.044 [-0.010, +0.102], p=0.375 | single-shot 9470 | 54.5 | 4.9 | 529 |
| `pc@1s + e5-base > mmarco@10` | 12 | 22 | 14 | 34 | 0.912 | 0.934 | 0.734 | 0.625 | +0.048 [-0.029, +0.135], p=0.453 | 665 / 1058 | 139.2 | 9.8 | 292 |
| `pc@1s + e5-base > bge@10` | 12 | 23 | 16 | 35 | 0.925 | 0.944 | 0.781 | 0.708 | +0.060 [-0.008, +0.140], p=0.219 | single-shot 9268 | 139.2 | 9.8 | 304 |
| `structure@300 + e5-base > mmarco@10` | 12 | 22 | 13 | 34 | 0.912 | 0.934 | 0.674 | 0.583 | +0.048 [-0.029, +0.135], p=0.453 | 662 / 1107 | 126.6 | 5.33 | 292 |
| `structure@300 + e5-base > bge@10` | 12 | 23 | 14 | 35 | 0.925 | 0.944 | 0.701 | 0.625 | +0.060 [-0.008, +0.140], p=0.219 | single-shot 9410 | 126.6 | 5.33 | 304 |

Source attribution within the Matcher settings is 100% by construction (job-ID filter; ESCO entries are atomic).

## Findings

1. **No configuration is significantly better than the baseline on the Matcher settings.** The best,
   `structure + e5-small > bge@20`, gains +0.065 MRR (CI [−0.010, +0.150], 1 vs 5 discordant queries, p = 0.22).
2. **Chunk size**: 300 words is the best structure setting (150: −0.060, CI excludes 0; 500: −0.021). Sliding windows
   are worse than structure at every size tried.
3. **Parent-child**: the 3-sentence window (stride 2) is the best chunker (+0.037, p = 0.38) at the same latency as
   the baseline (p95 132 vs 128 ms) — the cheapest promising change, but not significant.
4. **e5-base**: +0.033 on Matcher (French queries), worse on all-jobs MRR (0.437 vs 0.527); 2.5x indexing time.
5. **Rerankers**: the English MiniLM reranker hurts Matcher MRR; mmarco (multilingual) helps slightly at
   430–920 ms median; bge is best on quality but 3.5–10 s per query on CPU. Top-5 vs top-20: deeper candidate
   lists help all-jobs retrieval (bge 0.598 → 0.733) more than job-filtered retrieval.
6. **Int8**: bge-int8@10 keeps quality (0.912 vs 0.908) at ~2x speed but still 4–6 s p95; mmarco-int8 loses
   quality (0.838 vs 0.887). Quantisation is not a free win.
7. **Combinations** do not add up: parent-child + e5-base + bge@10 (0.925) is not better than bge@20 alone (0.929).
8. **All-jobs setting** (stress test): reranking is the only consistent large gain (0.527 → up to 0.781), consistent
   with exp02 — useful if a cross-posting search is ever needed, not for the Matcher, which always filters by job.

## Abstention (calibration split, 40 queries: 20 answerable, 20 unsupported)

`results/calibration_summary.md`. 5-fold CV accuracy (chance 0.5): baseline cosine ESCO 0.95, job-filtered 0.85;
bge@5 reranker score 0.95 / 0.95; mmarco 0.85–0.90 (not better than cosine). **Transfer check on natural dev
queries**: with the calibrated thresholds the baseline wrongly abstains on 8 of 40 answerable dev queries (6 of them
answered correctly at rank 1); bge@5 on 6 of 40. Cause: the calibration positives are template-generated and easier
than natural queries, so the thresholds are too strict. **Abstention is therefore not enabled by default**; it is
available as an opt-in experimental profile and must be recalibrated on natural, human-reviewed queries.

## Decision (pre-registered rule, `results/selection.md`)

| Profile | Budget | Best in budget (dev Matcher MRR) | Significant? | Selected |
|---|---|---|---|---|
| Real-time | p95 ≤ 300 ms | parent-child 3-sentence + e5-small (0.902, p95 132 ms) | no (CI [−0.013, +0.100]) | **structure + e5-small (baseline)** |
| Async | p95 ≤ 2 s | parent-child + e5-base + mmarco@10 (0.912, p95 1.06 s) | no (CI [−0.029, +0.135]) | **structure + e5-small (baseline)** |

Is the 300 ms limit too restrictive? Under the separately justified 2 s async budget, the extra quality available
(+0.048 MRR at most within budget) is still not distinguishable from noise on 40 queries, and it costs ~6x latency,
a second model (~0.3–0.5 GB) and a parent-child index (~9x more job vectors: 1,725 vs 197). A strict reading of the evidence does not
justify the added complexity yet. The bge reranker's larger gain (+0.065, and +0.21 on all-jobs) needs a GPU or offline
batching to fit any interactive budget.

## What would change the decision

Human review of the sealed final test set (36 queries), then one evaluation of baseline vs the two in-budget
candidates (`pc@3s2 + e5-small`, `pc@1s + e5-base > mmarco@10`). With ~76 Matcher queries (dev + test) a +0.04 MRR
effect could become detectable. Natural-query calibration would decide whether abstention can be enabled.

## Limitations

- 42 dev queries and many configurations: winner's-curse risk; differences are not significant.
- The exp02 holdout was inspected and is not reused; the new final test set is unreviewed and unevaluated.
- Calibration split is template-generated (some awkward wording, easy positives); thresholds did not transfer.
- CPU-only latency on a shared cloud container; RAM numbers are process RSS growth (indicative only).
- One run per configuration for quality (deterministic); repeats only for latency.

## Erratum (audit, 2026-10-15)

The dev grid contained **27** configurations (8 chunk tuning, 2 embedding, 9 rerankers, 2 int8, 6 combinations), i.e.
26 paired comparisons against the baseline; summaries elsewhere said 28. All per-configuration numbers are unaffected
(recomputed exactly by `rag/audit/recompute.py`). With a Holm correction for the 26 comparisons, every adjusted
p-value is 1.0.
