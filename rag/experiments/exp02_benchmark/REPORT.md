# Experiment 02 — extended chunking and retrieval benchmark (2026-10-14)

Pre-registration: `PLAN.md` (commit `22e5f13`, before any run). Raw outputs: `results/` (`dev_per_query.csv`,
`dev_configs.csv`, `dev_summary.md`, `holdout_*`, `esco_equivalence.md`). Selection frozen in `selection.json`
(commit `85e2676`) before the holdout was run. Nothing outside this folder was changed; the production API,
Matcher contract and the original/reviewed benchmarks are untouched.

Hardware and procedure (identical for all runs): cloud container, 4 CPU cores, no GPU, 15 GB RAM; CPU inference;
exact cosine search in numpy for every dense model; one warm-up query; per-query wall time.

## Status of every method

| Category | Method | Status |
|---|---|---|
| Chunking | fixed (200 words, no overlap) | tested |
| Chunking | structure-aware (production) | tested |
| Chunking | recursive (paragraph → line → sentence → word, ≤ 200 words) | tested |
| Chunking | semantic (break below the 25th percentile of adjacent-sentence e5-small similarity, ≤ 300 words) | tested |
| Chunking | sliding window (200 words, 30 overlap; the earlier "fixed") | tested |
| Chunking | sentence-based (5 sentences) | tested |
| Chunking | parent-child (sentence children with Job/Section header → structure parent returned) | tested |
| Lexical retrieval | BM25 (`bm25s`), TF-IDF (scikit-learn, sublinear tf, English stop words) | tested |
| Dense embeddings | multilingual-e5-small, all-MiniLM-L6-v2, multilingual-e5-base, BGE-M3 | tested |
| Fusion | RRF (k = 60) of BM25 + e5-small, BM25 + BGE-M3 | tested |
| Reranking | cross-encoder `BAAI/bge-reranker-v2-m3` over top-20 of e5-small dense | tested |
| Reranking | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (planned fallback) | skipped: the primary reranker ran |
| — | failed / unavailable | none |

BM25 and TF-IDF are lexical (sparse term-weighting) retrievers, not embedding models.

## Phase 1 — chunking (retriever fixed: e5-small dense; dev set, 42 queries)

| Chunker | Job chunks | Mean words | Coverage | Chunking s | Index s | Index MB | Matcher MRR | Scoped Hit@1 (/24) | Global Hit@1 (/24) | Global MRR |
|---|---|---|---|---|---|---|---|---|---|---|
| structure (baseline) | 197 | 191 | 100% | <0.1 | 51.6 | 2.66 | 0.865 | 20 | 10 | 0.527 |
| fixed | 190 | 190 | 100% | <0.1 | 48.8 | 2.65 | 0.858 | 20 | 6 | 0.360 |
| sliding | 218 | 193 | 100% | <0.1 | 50.6 | 2.69 | 0.835 | 18 | 9 | 0.467 |
| recursive | 296 | 122 | 100% | <0.1 | 50.0 | 2.81 | 0.835 | 18 | 6 | 0.355 |
| sentence | 353 | 102 | 100% | <0.1 | 50.4 | 2.89 | 0.856 | 20 | 12 | 0.588 |
| semantic | 463 | 78 | 100% | 23.1 (sentence embeddings) | 49.1 | 3.05 | 0.860 | 20 | 7 | 0.459 |
| parent-child | 1,725 children | 29 | 100% | <0.1 | 55.9 | 4.90 | **0.885** | **22** | 10 | 0.572 |

Index time includes encoding the 1,621 ESCO entries (~45 s), identical for every chunker. ESCO results are
identical across chunkers (11/16 Hit@1, MRR 0.786) because ESCO is always one entry = one chunk.
With BM25 as retriever, sliding and sentence chunking score best (scoped 21/24), structure 19/24: chunking
interacts with the retriever, as already seen in experiment 01.

**ESCO equivalence** (`results/esco_equivalence.md`): on the 1,621 ESCO entries (39 words on average), fixed,
structure, recursive, sliding and parent-child produce exactly one chunk per entry (identical boundaries);
sentence splits 8 entries; semantic splits 1,350 entries (it separates the skill label sentence from its
description). This justifies indexing ESCO atomically.

## Phase 2 — retrieval (chunking fixed: structure; dev set)

| Category | Retriever | ESCO MRR (16) | Scoped Hit@1 / MRR (24) | Global Hit@1 / MRR (24) | Matcher MRR / nDCG@10 | Median / p95 ms | Index s | Index MB | Model RAM MB |
|---|---|---|---|---|---|---|---|---|---|
| Lexical | BM25 | 0.559 | 19 / 0.844 | 11 / 0.542 | 0.730 / 0.765 | 0.2 / 0.3 | 0.1 | 0.44 | 0 |
| Lexical | TF-IDF | 0.553 | 20 / 0.865 | 11 / 0.545 | 0.740 / 0.773 | 1.0 / 1.4 | 0.4 | 0.52 | 0 |
| Dense | all-MiniLM-L6-v2 (English) | 0.740 | 13 / 0.726 | 5 / 0.365 | 0.732 / 0.780 | 101 / 117 | 21 | 2.66 | 76 |
| Dense | **e5-small (baseline)** | 0.786 | 20 / 0.917 | 10 / 0.527 | 0.865 / 0.893 | 112 / 175 | 52 | 2.66 | 379* |
| Dense | e5-base | **0.806** | 22 / 0.958 | 7 / 0.437 | 0.897 / 0.923 | 142 / 171 | 142 | 5.33 | 384* |
| Dense | BGE-M3 | 0.719 | 21 / 0.931 | 12 / 0.613 | 0.846 / 0.878 | 219 / 319 | 533 | 7.10 | 235* |
| Fusion | BM25 + e5-small (RRF) | 0.696 | 20 / 0.917 | 12 / 0.573 | 0.829 / 0.865 | 108 / 133 | 52 | 3.10 | 379* |
| Fusion | BM25 + BGE-M3 (RRF) | 0.710 | 21 / 0.938 | 12 / 0.595 | 0.847 / 0.879 | 218 / 349 | 533 | 7.54 | 235* |
| Reranking | e5-small → bge-reranker-v2-m3 (top 20) | **0.854** | **23 / 0.979** | **15 / 0.733** | **0.929 / 0.947** | 9,443 / 19,109 | 52 | 2.66 | 890* |

\* RSS growth when the model was loaded, measured in one long-running process; the first model loaded also carries
PyTorch's own allocations, so these numbers are indicative, not exact model sizes.
No-answer: every dense, fusion and reranking configuration returns results for both off-domain dev queries
(0/2 `no_match`); BM25 and TF-IDF return nothing for 1 of 2.

## Uncertainty (paired against the baseline, dev set)

Full table in `results/dev_summary.md`. On the Matcher settings (ESCO + job-filtered, 40 query-settings):

| Candidate | Baseline-only / candidate-only Hit@1 | McNemar p | MRR diff, bootstrap 95% CI |
|---|---|---|---|
| e5-small → reranker | 1 / 5 | 0.22 | +0.065 [−0.010, +0.150] |
| e5-base | 2 / 4 | 0.69 | +0.033 [−0.036, +0.102] |
| parent-child chunking | 2 / 4 | 0.69 | +0.021 [−0.042, +0.087] |
| BGE-M3 | 5 / 5 | 1.00 | −0.019 [−0.110, +0.071] |
| BM25 | 7 / 2 | 0.18 | −0.135 [−0.235, −0.041] |
| all-MiniLM-L6-v2 | 9 / 2 | 0.07 | −0.133 [−0.233, −0.033] |

Global setting: only the reranker's gain has a CI excluding 0 (+0.206 [+0.047, +0.367]).

## Selection (pre-registered rule applied by `analyze.py`)

No candidate met the rule (significant Matcher gain **and** ≤ 300 ms median **and** no extra service).
**Production configuration unchanged: structure-aware chunking + multilingual-e5-small dense.** Why each part wins:

- **Chunking — structure-aware.** Best Matcher MRR of the one-vector-per-chunk methods (0.865; sentence 0.856,
  semantic 0.860, fixed 0.858), ties the best scoped Hit@1 among them (20/24), third-best global MRR (0.527, behind
  sentence 0.588 and parent-child 0.572), few chunks (197), and it returns a section label the Matcher can cite. Parent-child is the strongest chunker (+0.021 MRR, n.s.) but needs ~9x more
  vectors and a child-to-parent mapping; not justified by a non-significant gain.
- **Embedding — e5-small.** e5-base is +0.033 MRR (n.s.) at 2.7x the indexing time and 2x the index size; BGE-M3
  is not better and 2x slower; MiniLM is English-only and clearly worse (−0.133, CI excludes 0). Lexical BM25 /
  TF-IDF are clearly worse on the Matcher settings (CI excludes 0) and fail French queries.
- **Fusion — not used.** RRF lowers ESCO MRR (0.696 vs 0.786) and does not raise Matcher MRR.
- **Reranking — not used in production on CPU.** It is the largest quality gain measured in this project
  (dev Matcher +0.065, global +0.206 CI > 0) but costs ~9 s per query on this CPU and ~0.9 GB more RAM, which
  fails the latency limit. It is the first upgrade to consider if a GPU is available or if the Matcher can batch
  queries offline.

## Holdout (30 queries, run once after the selection was frozen)

| Configuration | ESCO Hit@1 / MRR (10) | Scoped Hit@1 / MRR (16) | Global Hit@1 / MRR (16) | Matcher MRR / nDCG@10 | No-answer | Median ms |
|---|---|---|---|---|---|---|
| baseline (structure + e5-small) | 8 / 0.883 | 9 / 0.752 | 4 / 0.359 | 0.803 / 0.853 | 0/4 | 106 |
| e5-small → reranker (best dev candidate, not selected) | 8 / 0.883 | 14 / 0.927 | 9 / 0.610 | 0.910 / 0.933 | 0/4 | 8,695 |

Reranker vs baseline on holdout: candidate-only Hit@1 5 vs 0 on both Matcher and global settings (McNemar p = 0.062
each); MRR diff +0.108 [+0.019, +0.210] (Matcher) and +0.251 [+0.068, +0.448] (global). The holdout confirms
the reranker's direction of effect on unseen queries; it was **not** used to change the selection.
The baseline's holdout job-filtered score (9/16 Hit@1) is lower than on dev (20/24): dev numbers are optimistic,
as expected for a development set.

## Limitations

- Small samples: 42 dev and 30 holdout queries; most differences are not significant.
- Holdout authored by Claude (same author family as the dev drafts), not human-annotated, not reviewed.
- One run per configuration; latency measured on a shared cloud CPU (noise possible), not on the demo laptop.
- Memory measured as process RSS growth in one long process (indicative only).
- Chunker parameters were set once from the documented defaults (200 words, 5 sentences, 25th percentile),
  not tuned; tuning could change the ranking among chunkers.
- Sentence segmentation is regex-based (abbreviations such as "e.g." split sentences).
- The reranker sees chunk text only up to 512 tokens.

## Reproduce

```bash
cd rag/experiments/exp02_benchmark
HF_HOME=<cache> CUDA_VISIBLE_DEVICES= python run.py dev && python analyze.py dev       # writes selection.json
HF_HOME=<cache> CUDA_VISIBLE_DEVICES= python run.py holdout && python analyze.py holdout
HF_HOME=<cache> CUDA_VISIBLE_DEVICES= python esco_equivalence.py
```
