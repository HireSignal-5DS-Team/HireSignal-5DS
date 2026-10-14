# Audit of experiment 02 (2026-10-14)

Source: `../exp02_benchmark/results/dev_per_query.csv`, paired per (query, setting) against the baseline
(structure + e5-small dense). "Improved" = better first-hit rank.

| Candidate | Improved | Worsened | Where it wins | Where it loses | Explanation |
|---|---|---|---|---|---|
| e5-small → bge-reranker-v2-m3 | 17 | 4 | French (E02 rank >10 → 1, E08, J18), all-jobs queries (J09 10 → 1, J16 9 → 1, J17 4 → 1), job-filtered ties (J03, J05, J20) | generic/ambiguous queries (E10 "cross-functional teams", E13 "image recognition", J02 citizenship in all-jobs) | A cross-encoder reads query and passage together (full attention), instead of comparing two independently pooled vectors; it can use exact phrasing and negation. Cost: one transformer pass per candidate. |
| parent-child (e5-small) | 11 | 8 | gold = one sentence inside a long section (J03, J05, J19 "Python required", J20) | evidence spread over a section or generic (J16, J23 1 → 3) | A 29-word child vector is precise for a one-sentence requirement but noisy for multi-sentence evidence: a granularity trade-off. |
| e5-base | 13 | 12 | French queries (E02, E08, J07, J13) | several all-jobs queries (J01, J02, J11, J21) and two ESCO queries (E04, E07) | Larger multilingual model helps cross-lingual matching; the net effect on this set is noise-level. |

## Weaknesses found

1. **Job filtering**: in the all-jobs setting, generic requirements (citizenship, degree, IT competencies) occur in many
   postings, so "wrong posting" is often correct content. The Matcher always knows the job: **job-ID filtering must
   be mandatory for job-specific retrieval**; all-jobs numbers are a stress test, not the product metric.
2. **ESCO retrieval**: the English-only index makes French queries the main failure (E02 missed by e5-small);
   tool-level skills (Power BI, PyTorch, Kubernetes) are absent from ESCO and map to broader concepts.
3. **No-answer handling**: dense and reranking configurations never abstain (0/2 dev, 0/4 holdout). More importantly,
   **no benchmark so far tests the realistic job-scoped case**: the Matcher asks for a requirement the posting does
   not contain. That case needs its own data and a calibrated abstention score.
4. **Evaluation**: 42 dev queries, many configurations: risk of picking a winner by chance (winner's curse). The exp02
   holdout has now been inspected and cannot serve as an unbiased final test.
