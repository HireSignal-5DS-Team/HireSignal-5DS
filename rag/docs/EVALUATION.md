# Retrieval evaluation (runs of 2026-10-13)

Status: **complete** for ESCO (part 1) and for the 20 job postings, including the chunking comparison (part 2).
The ESCO numbers in part 1 come from the ESCO-only run; in the final combined run BM25 ESCO Hit@5 moves from
10 to 11 (fixed) because BM25 term statistics are now computed over ESCO + job chunks. Dense results are unchanged.
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


# Part 2 — Job postings and chunking comparison (final run)

Reproduce: `HF_HOME=<cache> CUDA_VISIBLE_DEVICES= python rag/evaluate.py --models e5-small bge-m3`
(preliminary 5-posting run: `--batch prelim`, results in `eval/results_prelim/`).

## Setup

- Corpus: 20 real USAJOBS announcements (36,000 words), see `SOURCES.md`; frozen before the 15 final queries were written.
- Chunking: **S1 fixed** 200 words / 30 overlap → 218 chunks, mean 193 words.
  **S2 structure** (page headings, `Job | Section` prefix, long sections split at sentence boundaries)
  → 197 chunks, mean 191 words. Chunk sizes are matched, so differences come from boundaries and prefixes.
- Queries: 25 (20 English, 5 French), one gold verbatim quote each; a chunk is a hit if it covers >= 50% of the
  quote. AI-drafted, to be verified by a teammate.
- Settings: **scoped** = filtered to the gold posting (how the Matcher calls the RAG: it knows the job);
  **global** = all 20 postings (harder: the right posting must also be found).

## Results (Hit@1 / Hit@5 out of 25, MRR@10, ms/query on 4-core CPU)

| Retriever | Fixed scoped | Structure scoped | Fixed global | Structure global |
|---|---|---|---|---|
| BM25 | 20 / 22, 0.840 | 18 / 21, 0.777 | 11 / 20, 0.575 | 12 / 15, 0.559 |
| e5-small dense | 18 / 25, 0.853 | 19 / 25, 0.880 | 8 / 16, 0.455 | 10 / 17, 0.531 |
| e5-small hybrid | **23** / 25, **0.960** | 20 / 25, 0.888 | 10 / 18, 0.532 | 12 / 17, 0.581 |
| bge-m3 dense | 19 / 25, 0.870 | **23** / 25, 0.953 | 8 / 16, 0.431 | **14** / 20, **0.662** |
| bge-m3 hybrid | 21 / 25, 0.920 | 22 / 25, 0.940 | 10 / 19, 0.529 | 13 / 21, 0.628 |

Latency: BM25 < 1 ms; e5-small 100–115 ms; bge-m3 280–310 ms per query.

## Paired significance (exact McNemar test on Hit@1; "A-only / B-only" = queries only A or only B gets right)

| Comparison (A vs B) | A-only | B-only | p |
|---|---|---|---|
| fixed vs structure, bge-m3 dense, global | 1 | 7 | 0.07 |
| fixed vs structure, bge-m3 dense, scoped | 2 | 6 | 0.29 |
| fixed vs structure, e5-small dense, global | 1 | 3 | 0.63 |
| fixed vs structure, e5-small hybrid, scoped | 4 | 1 | 0.38 |
| fixed vs structure, BM25, scoped | 2 | 0 | 0.50 |
| e5-small vs bge-m3, structure dense, global | 3 | 7 | 0.34 |
| e5-small vs bge-m3, structure dense, scoped | 1 | 5 | 0.22 |

## Comments

1. **Chunking: structure-aware helps the dense models, fixed-size helps BM25; no difference is significant at
   p < 0.05 with 25 queries.** The clearest effect is bge-m3 dense in the global setting (14 vs 8 Hit@1, MRR
   0.662 vs 0.431, p = 0.07). Likely mechanism: the `Job: <title> | Section: <name>` prefix tells a dense model
   which posting and which part a chunk belongs to, which matters most when it must pick among 20 postings.
   BM25 does not benefit because the prefix adds the same words to every chunk of a posting.
2. **The preliminary run was misleading.** On 5 postings / 10 queries, fixed-size looked equal or better
   (scoped e5 dense 8 vs 7). With 20 postings / 25 queries the direction reversed for dense models. This is
   why we froze a larger corpus before deciding.
3. **Our original hypothesis (keeping must-have and nice-to-have apart) could not be tested on this corpus**:
   USAJOBS pages have coarse headings ("Qualifications" holds ~1,300 words on one line), so S2 must split by
   sentences anyway. Private-sector ads with "Requirements / Nice to have" headings would test it directly.
4. **Model**: bge-m3 is ahead on job postings (scoped 23 vs 19, global 14 vs 10) but not significantly, while
   e5-small is ahead on ESCO (10 vs 9) and 3x faster. By our pre-set rule (keep the larger model only if it
   clearly wins), e5-small stays the default; bge-m3 remains a one-variable switch (`RAG_MODEL=bge-m3`).
5. **Hybrid**: on job postings it helps e5-small (scoped 23 vs 18 with fixed chunks) but not bge-m3; on ESCO it
   hurts. No uniform winner.
6. **Global failures are mostly underspecified queries**, not retrieval errors: "exigence de nationalité pour ce
   poste" (citizenship) or "compétences informatiques exigées" match requirements that every federal posting
   has; the top results are correct passages from other postings. In production the Matcher always passes
   `job_id`, i.e. the scoped setting, where the best configurations reach 23/25 Hit@1 and 25/25 Hit@5.
7. **Abstention re-check**: with job queries added, the even/odd threshold calibration again selects a threshold
   that abstains on nothing; held-out accuracy (e5-small 20/22, bge-m3 18/22) is at or below the trivial
   "always answer" baseline (20/22). Decision D6 (no cosine threshold) stands.

## Error examples (global setting)

| Query | Config | Gold rank | What was retrieved |
|---|---|---|---|
| J02 "exigence de nationalité pour ce poste" (FR) | structure, bge-m3 | 4 | citizenship conditions of 3 other postings (correct content, wrong posting) |
| J07 "responsabilités principales : stratégie d'ingénierie pour les systèmes d'IA et le cloud" (FR) | structure, bge-m3 | 10 | duties of the Senior Cloud AI Engineer posting, which genuinely matches the description |
| J09 "which deep learning frameworks does the role use" | structure, e5-small | 7 | other data-science postings; "the role" gives no clue which posting is meant |
| J22 "compétences informatiques exigées pour ce poste" (FR) | fixed, e5-small | >10 | IT competency text of other 2210-series postings |

# Part 3 — Reviewed labels and re-evaluation (2026-10-14)

Review provenance: **user-approved AI-assisted review**, not independent human annotation (details and
per-correction source checks: `eval/review/VALIDATION.md`; full changelog: `eval/review/changelog.md`).
Reviewed set: 42 queries (16 ESCO, 24 job, 2 no-answer); J22 rejected and excluded from all denominators.
Same frozen configurations, corpus, index and code as part 2; only the labels changed.
Outputs: `eval/results_queries_reviewed/` (summary, results, rankings) and `comparison.md`.
Original results in `eval/results/` are unchanged.

## Default configuration (structure chunking, e5-small dense)

| Collection | Labels | n | Hit@1 | Hit@5 | MRR@10 | nDCG@10 |
|---|---|---|---|---|---|---|
| ESCO | original | 14 | 10 | 13 | 0.804 | 0.835 |
| ESCO | reviewed | 16 | 11 | 15 | 0.786 | 0.825 |
| Jobs, scoped (Matcher setting) | original | 25 | 19 | 25 | 0.880 | 0.911 |
| Jobs, scoped (Matcher setting) | reviewed | 24 | 20 | 24 | 0.917 | 0.938 |
| Jobs, global | original | 25 | 10 | 17 | 0.531 | 0.604 |
| Jobs, global | reviewed | 24 | 10 | 16 | 0.527 | 0.589 |
| No-answer (correct = `no_match`) | original | 4 | 0 | | | |
| No-answer (correct = `no_match`) | reviewed | 2 | 0 | | | |

Recall@k equals Hit@k here (one relevant item counted per query). nDCG@10 = mean of 1/log2(rank+1) for the first
gold hit. Latency is unchanged (~100 ms/query for e5-small on the 4-core CPU).

## What changed and why

- ESCO: N01 (Kubernetes) and N02 (Power BI dashboards) became answerable ESCO queries; e5-small finds the new gold at
  rank 1 and rank 3. E14 gained a 4th valid URI. Net: 11/16 Hit@1.
- Jobs: per-query ranks changed only for J04 (rank 2 → 1 after rewording) and J22 (removed). Gold replacements
  J06, J17, J19 left the first-hit rank of the default configuration unchanged.
- No-answer: only the two off-domain controls remain; every dense configuration still returns results for them,
  BM25 returns nothing for 1 of 2. Consistent with decision D6 (no cosine threshold; the Matcher must check labels).

## Is structure-aware chunking + e5-small still justified?

Yes, with the same caveats as before. Exact McNemar tests on Hit@1, reviewed labels:

| Comparison | A-only | B-only | p |
|---|---|---|---|
| fixed vs structure, e5-small dense, scoped | 1 | 3 | 0.63 |
| fixed vs structure, e5-small dense, global | 2 | 3 | 1.00 |
| fixed vs structure, bge-m3 dense, global | 1 | 6 | 0.13 |
| e5-small vs bge-m3, structure dense, scoped | 2 | 3 | 1.00 |
| e5-small vs bge-m3, structure dense, global | 3 | 5 | 0.73 |

Structure-aware chunking stays ahead for dense models (not significant). The e5-small vs bge-m3 gap on job
postings shrinks to one query in the scoped setting (20 vs 21 Hit@1), while e5-small remains ~2.5x faster,
so the pre-set rule (keep the larger model only if it clearly wins) still selects e5-small.

## Anomaly

In the reviewed run, fixed-chunking + bge-m3 dense latencies are inflated (median 770–920 ms, one 103 s outlier)
while all other configurations match part 2. The retrieval code and index are identical, so we attribute it to
CPU contention in the shared container; use the part-2 latency for that configuration.
