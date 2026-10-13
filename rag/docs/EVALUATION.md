# Retrieval evaluation — ESCO collection (run 2026-10-13)

Status: **ESCO part complete; job-posting part (and the chunking comparison) pending the job corpus.**
Raw outputs: `eval/results/summary.md`, `results.csv`, `rankings.jsonl` (top-3 per query and configuration).
Reproduce: `HF_HOME=<cache> CUDA_VISIBLE_DEVICES= python rag/evaluate.py --models e5-small bge-m3`.

## Setup

- Corpus: 1,621 ESCO v1.1.x (en) skill concepts, one concept per chunk (see `SOURCES.md`).
- Queries: 14 skill-mention queries with gold ESCO URIs (12 English, 2 French) + 4 queries with no correct
  ESCO concept (Kubernetes, Power BI, pastry baking, truck licence). **All 18 are AI-drafted; gold URIs were
  resolved by exact ESCO label, not by looking at retrieval output. A teammate must verify them.**
- Configurations: BM25 (`bm25s`), dense `intfloat/multilingual-e5-small` (118M params, 384-d) and
  `BAAI/bge-m3` (568M params, 1024-d), and hybrid BM25+dense with RRF (k=60). Top-k = 10 for scoring.
- Hardware: cloud container, 4 CPU cores, no GPU. Latency = mean wall time per query, including query encoding.
- Chunking strategy does not apply to ESCO (atomic entries), so the `fixed` and `structure` rows are identical
  by construction; only `structure` is shown below.

## Results (hits out of 14 answerable queries)

| Retriever | Hit@1 | Hit@5 | MRR@10 | ms/query |
|---|---|---|---|---|
| BM25 | 7 | 10 | 0.616 | 0.7 |
| e5-small dense | **10** | 13 | **0.804** | 101 |
| e5-small hybrid | 8 | 13 | 0.708 | 107 |
| bge-m3 dense | 9 | 13 | 0.751 | 251 |
| bge-m3 hybrid | 8 | **14** | 0.740 | 253 |

## Comments

1. **Dense beats BM25 clearly**: +2 to +3 Hit@1 and +3 to +4 Hit@5. BM25 has no result for the French query
   "apprentissage automatique" and ranks the gold concept 7th for "writing SQL queries against relational
   databases" and "image recognition" (lexical mismatch).
2. **e5-small vs bge-m3**: no meaningful quality difference on 14 queries (10 vs 9 Hit@1; differences of 1–2 hits
   are within noise at this sample size), but e5-small is ~2.5x faster on CPU and ~5x smaller.
   **Decision: e5-small** (justified simplicity). BGE-M3 is the better French model in this run: it finds
   "apprentissage automatique" (rank 5) where e5-small fails.
3. **Hybrid did not help on ESCO**: it lowers Hit@1 for both models (BM25 promotes lexically similar but wrong
   concepts). It raises Hit@5 for bge-m3 to 14/14. ESCO entries are short label lists where dense matching is
   enough. Hybrid is kept as a candidate for job postings, where exact tool names matter; to be measured.
4. **Abstention by cosine threshold failed** (negative result). Threshold chosen on even query ids, tested on odd:
   accuracy 7/9 for both models, which equals the trivial "always answer" baseline. Reason: the in-domain
   unanswerable tools score like answerable queries (e5-small: Kubernetes 0.828, Power BI 0.849 vs answerable
   minimum 0.804; bge-m3: 0.551 / 0.564 vs minimum 0.529). Off-domain queries (pastry, truck licence) do fall
   below the answerable range, but a single global threshold cannot separate the two. e5-small scores are
   compressed in 0.78–0.90, a known property of this model family, so cosine values must not be read as
   confidence. **Decision: no cosine threshold**; `no_match` only when nothing is retrieved, and the Matcher
   must check that a retrieved concept actually names the skill (label match) before using it.

## Error examples

| Query | Retriever | Gold rank | Top-3 retrieved | Why |
|---|---|---|---|---|
| apprentissage automatique (FR) | e5-small dense | >10 | use automatic programming; demonstrate willingness to learn; apply blended learning | Surface-level cross-lingual matching ("automatique", "apprentissage") |
| building ETL pipelines | bge-m3 dense | 7 | install low voltage wiring; install electronic communication equipment; engineering processes | "pipelines" read as physical installation; BM25 and e5 get it right |
| writing SQL queries against relational databases | e5-small dense | 4 | operate relational database management system; NoSQL; design database scheme | Arguably a gold-label ambiguity: rank 1 is also a reasonable answer |
| Power BI dashboards (no answer) | e5-small dense | n/a | IBM InfoSphere DataStage; database management systems; business intelligence | Unknown tool mapped to nearby concepts with high cosine (0.849) |

## Limitations

14 answerable queries are a small sample; we report hit counts, not percentages, and claim only differences
that are consistent across metrics. Queries and gold labels are AI-drafted and unverified. Latency was
measured on a 4-core cloud CPU, not the demo laptop.
