# Experiment 02 — extended chunking and retrieval benchmark (pre-registration)

Written and committed **before** any experiment in this folder was run. Nothing outside this folder is modified;
the production configuration (structure chunking + e5-small dense) stays the baseline.

## Data splits

| Split | File | Use |
|---|---|---|
| Development | `rag/eval/queries_reviewed.jsonl` (42 queries: 16 ESCO, 24 job, 2 no-answer) | all comparisons and configuration selection |
| Holdout | `holdout_queries.jsonl` (30 queries: 10 ESCO, 16 job, 4 no-answer; 6 French), SHA256 `d06c05d1…eb60` | evaluated **once**, only for the baseline and the configuration selected on dev |

Holdout provenance: written by Claude in a separate authoring pass, using ESCO concepts and posting passages that
are not dev gold; every gold URI was checked to exist in the 1,621 subset, every gold quote to occur verbatim in
its posting, every no-answer term to match no subset entry. It is **not** independently authored by a human and
has not been human-reviewed; it shares the author of the dev drafts. It reduces, but does not remove, optimism.

## Matrix (one variable changed at a time)

| Phase | Varied | Fixed |
|---|---|---|
| 1 chunking | fixed (200 w, no overlap), structure (production), recursive, semantic, sliding window (200 w / 30 overlap = old "fixed"), sentence-based, parent-child | retriever = e5-small dense (and BM25 as model-free check); ESCO = one entry per chunk |
| 2a lexical | BM25, TF-IDF | structure chunking |
| 2b dense embeddings | e5-small, all-MiniLM-L6-v2, multilingual-e5-base, bge-m3 | structure chunking; exact cosine search (numpy) for all |
| 2c fusion | BM25 + dense with RRF (k=60) | structure chunking |
| 2d reranking | cross-encoder over top-20 of a first-stage retriever | structure chunking |

## Measurements

Hit@1/5/10 (= Recall@k, one relevant item counted per query), MRR@10, nDCG@10; per-query latency median and p95
(warm models, one warm-up query excluded); indexing time; model memory (RSS delta from /proc); index size;
chunk counts and source-coverage. Reported separately for ESCO, job-filtered (scoped), global job and no-answer.
Uncertainty: paired bootstrap 95% CI (2,000 resamples, seed 0) of the MRR difference against the baseline,
exact McNemar test on Hit@1.

## Selection rule (fixed in advance)

Replace a production component only if a candidate, on the **dev** set, (1) improves Hit@1 or MRR in the
Matcher-relevant settings (ESCO + job-filtered, pooled) with exact McNemar p < 0.05 or a bootstrap MRR-difference
CI excluding 0, (2) keeps median query latency <= 300 ms on this 4-core CPU, and (3) needs no extra running
service. Otherwise the baseline stays. Ties go to the simpler, faster option.
