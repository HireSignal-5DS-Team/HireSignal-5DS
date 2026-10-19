# RAG — knowledge base, chunking, retrieval and its effect on the Matcher (T09)

Written to be reused in the final report. All numbers are measured; labels say where (real-GPU = RTX 4050 Laptop).
RAG output is **knowledge, never evidence**: the query is the requirement (its skill terms or its text), never CV
text, and the Matcher's quotes must come from the CV (validator rule).

## 1. Corpus

| item | value |
|---|---|
| source | ESCO v1.1.1 (European Commission), **CC BY 4.0**, via the Tabiya CSV mirror (`tabiya-tech/taxonomy-model-application`, MIT repo; its data folder carries the ESCO CC BY 4.0 licence), commit `eb3e5f44`, files pinned by sha256 in `rag/build_esco.py` |
| selection | V2's rule: skills linked to occupations of ISCO groups 25 (ICT professionals), 35 (ICT technicians), 212 (mathematicians, statisticians), 1330 (ICT managers), plus all transversal skills |
| size | **1,621 concepts**: 1,106 skills/competences, 514 knowledge, 1 untyped; reuse level: 665 sector-specific, 452 cross-sector, 440 transversal, 64 occupation-specific |
| files | `rag/data/esco/esco_ict_skills.jsonl` (V2 file, sha256 `8c6a4b3d…`; **rebuilt byte-identical** by `rag/build_esco.py`), `rag/data/esco/esco_ict_graph.jsonl` (sha256 `4602627e…`): uri, label, alt_labels, description, type, reuse level, **broader** (skills + skill groups), **narrower**, **related** (skill-to-skill, essential/optional) |
| graph | all 1,621 have a broader link, 445 narrower, 603 related (median 0 related, median 4 alternative labels) |
| why it fits | it is the EU's skills vocabulary with alternative labels (synonyms, spellings) and a hierarchy, exactly what the Matcher lacks when a CV and a job name the same skill differently; free and licensed for reuse |
| known gaps | ESCO v1.1.1 has no concept for Spark, Kubernetes, data lake, AWS, PyTorch, microservices, AutoML: those requirements can only get the closest broader concept (e.g. Docker -> "manage ICT virtualisation environments") |

## 2. Chunking (one concept = one chunk; no concept is split)

| strategy | content | size (characters, median / p90 / max) | MiniLM tokens (median / p90 / max; > 256 cut) |
|---|---|---|---|
| **A** | `<label>. Also known as: <alt labels>. <description>` (= what the Matcher saw so far) | 255 / 444 / 1,297 | 48 / 80 / 406; 2 chunks above the 256-token window |
| **B** | A + `Broader: <labels>. Related: <labels (max 10)>.` | 342 / 556 / 1,426 | 63 / 99 / 429; 4 above 256 |

Why concept-level chunks: an ESCO entry is short and self-contained; splitting it would separate a label from its
definition. B tests whether neighbour labels help a query find the right concept. Overlap is not needed (no concept is
cut). The knowledge given to the Matcher is always the **A text, cut at 300 characters, k = 3 refs** (the format the
LoRA was trained on: V2 p1 `format_knowledge`); chunking only changes what is indexed. (The task text says 280; our
V0 and V2's prompt code use 300; kept at 300 so the format does not change.)

## 3. Retrieval evaluation set (`rag/eval/queries.jsonl`, made by `rag/eval/make_queries.py`)

46 queries with known ESCO answers (any listed concept counts), fixed before measuring, split dev 24 / test 22
(alternating within each source):
- 14 **V2 reviewed** English ESCO queries (V2 AI-assisted review approved by the V2 owner), e.g. "writing SQL queries
  against relational databases" -> SQL;
- 9 from our **T06 Matcher errors** (alias / buried-term misses), e.g. "PL/SQL" -> SQL, query languages;
  "Databricks Lakehouse Fundamentals" -> data warehouse; "AWS RDS, AWS Aurora Postgres" -> cloud technologies;
- 23 from our **gold requirements**, e.g. "asynchronous programming" -> use concurrent programming;
  "collaborative filtering" -> build recommender systems.
Gold for the 32 new queries was drafted by the Developer (AI) from exact ESCO labels, then **checked by the Approver** (2026-10-18, `rag/eval/queries_review.xlsx`): 22 OK, 10 CHANGE (more accepted concepts, e.g. "PL/SQL" also -> Oracle Relational Database), 0 DROP; applied by `scripts/apply_query_review.py` (pre-review file kept as `rag/eval/queries_drafted.jsonl`).
Metrics: hit@1, hit@3, MRR@10 (rank of the first gold concept), mean query latency.

## 4. Retrieval benchmark (golds checked by the Approver; real-GPU; choose on dev, report on test)

T09 ran the full 84-configuration grid (`rag/evaluate.py`, `eval/results/2026-10-18_rag_retrieval/`) on the drafted
golds and chose dense all-MiniLM-L6-v2 (dev MRR@10 0.762). T09b re-scored the configurations below on the checked
golds (`rag/rescore.py`, `eval/results/2026-10-18_rag_retrieval_checked/`); latency as in T09.

| configuration (chunking A unless noted) | dev hit@1 | dev hit@3 | dev MRR@10 | test hit@1 | test hit@3 | test MRR@10 |
|---|---|---|---|---|---|---|
| BM25 (V0, pre-T09 baseline) | 0.417 | 0.583 | 0.52 | 0.318 | 0.455 | 0.425 |
| BM25, chunking B | 0.417 | 0.583 | 0.516 | 0.318 | 0.455 | 0.412 |
| **dense all-MiniLM-L6-v2** | 0.75 | 0.833 | 0.798 | 0.591 | 0.864 | 0.712 |
| dense multilingual-e5-base | 0.625 | 0.833 | 0.723 | 0.318 | 0.773 | 0.556 |
| **dense bge-small-en-v1.5** | 0.792 | 0.833 | 0.824 | 0.5 | 0.682 | 0.609 |
| dense MiniLM, chunking B | 0.75 | 0.792 | 0.79 | 0.5 | 0.864 | 0.68 |
| hybrid MiniLM (RRF) | 0.583 | 0.792 | 0.686 | 0.545 | 0.818 | 0.684 |
| hybrid bge-small (RRF) | 0.625 | 0.792 | 0.712 | 0.591 | 0.727 | 0.662 |
| hybrid MiniLM + ms-marco rerank | 0.667 | 0.792 | 0.724 | 0.545 | 0.682 | 0.611 |
| hybrid MiniLM + rerank + graph | 0.667 | 0.792 | 0.732 | 0.545 | 0.636 | 0.583 |
| dense MiniLM + ms-marco rerank | 0.708 | 0.833 | 0.765 | 0.591 | 0.636 | 0.632 |
| dense MiniLM + bge-reranker-base | 0.458 | 0.708 | 0.609 | 0.409 | 0.727 | 0.587 |
| dense MiniLM + graph expansion | 0.75 | 0.792 | 0.798 | 0.591 | 0.773 | 0.692 |

Readings (dev, checked golds):
- **Dense beats BM25 clearly** (MiniLM MRR 0.798 vs 0.520): queries like "PL/SQL", "Lakehouse" or "asynchronous
  programming" share no word with the ESCO label; embeddings bridge that.
- **With the checked golds, bge-small-en-v1.5 has the highest dev MRR** (0.824 vs 0.798 for MiniLM). The gap comes from
  3 of 24 queries (O03 rank 8 -> 3, O22 3 -> 1, O24 2 -> 4), and hit@3 is equal (0.833).
  - **Decision (Approver, 2026-10-18):** treat it as a tie on dev and break the tie by the simpler, faster model.
  - **Production keeps all-MiniLM-L6-v2:** 6 layers vs 12, 91 MB vs 134 MB, no query instruction prefix, and about
    38 vs 57 ms per query in the T09 grid. It is also the model that V6's Matcher effect was measured with.
  - Reported only, not used for the choice: on test, MiniLM has MRR 0.712 vs 0.609.
- **Hybrid is worse than dense alone**: BM25's wrong hits pull RRF down on these short, synonym-heavy queries.
- **Rerankers do not help** on dev (ms-marco on dense: 0.765 vs 0.798; bge-reranker-base: 0.609): trained on web
  passage relevance (MS MARCO), not on short skill labels.
- **Chunking B and graph expansion do not help**: neighbour labels add noise to the index; expansion only reorders below
  the top hit.
- Latency (T09): grid numbers include each configuration's first (cold) query; warm dense queries take ~4-8 ms (section 5).

## 5. Vector store: Qdrant (local mode) vs Chroma (persistent local) — same MiniLM vectors, same chunks

| | numpy (brute force, reference) | **Qdrant local** | Chroma persistent |
|---|---|---|---|
| top-10 equal to numpy, 46 queries | 46/46 | **46/46** | 46/46 |
| warm query latency | 4.19 ms | 8.23 ms | 5.43 ms |
| build (index 1,621 vectors, embeddings cached) | 0.79 s | 4.22 s | 1.75 s |
| disk | 2.5 MB (in memory) | 6.7 MB | 4.5 MB |
| metadata filtering | code | payload filters | `where` filters |
| install effort | none | `qdrant-client` (already in our env) | `chromadb` + **36 more packages** (onnxruntime, kubernetes client, opentelemetry, …) |
| n8n | via our API | our API, or n8n's built-in **Qdrant Vector Store** node (server mode) | our API, or n8n's ChromaDB node (server mode) |

**Choice: Qdrant.** Retrieval quality is identical (exact top-10 on all queries); the latency difference (3 ms) does
not matter next to a 2-3 s Matcher call; Qdrant needs no extra dependency (Chroma adds 36 packages to our single
environment), and it is the store named in the Locked architecture. Chroma was installed only for this benchmark.

## 6. Effect on the Matcher (the real test): 52 real pairs, 364 gold rows, real-GPU

Each variant: Matcher LoRA (+ confidence rule, tau_conf 0.72) -> Judge (DeBERTa NLI) through the station API, then the
T08b gate offline (t_invite 85, pair flags info, Judge doubt on a MET must counts only if p(MET) < 0.999). V0 reuses
the T08b rows. Skill terms come from the Job Agent's T06 terms, kept when written in the requirement
(`scripts/add_skill_terms.py`). Script: `scripts/eval_rag_matcher.py`; results:
`eval/results/2026-10-18_rag_matcher/summary.json` + `rows_V*.jsonl`. Dev and test: 182 rows / 26 pairs each.

| variant | dev macro-F1 | dev F1 MET / MISSING / UNC | dev false MET | dev UNC recall | dev gate FI / FR / review | test macro-F1 | test false MET | test gate FI / FR / review | ms RAG / s match |
|---|---|---|---|---|---|---|---|---|---|
| V0 BM25, whole sentence (baseline) | 0.651 | 0.772 / 0.843 / 0.339 | 10 | 0.370 | 0 / 6 / 0.077 | 0.661 | 13 | 0 / 4 / 0.154 | - / 3.2* |
| V1 BM25 + skill terms | 0.579 | 0.760 / 0.806 / 0.172 | 10 | 0.185 | 0 / 6 / 0.077 | 0.661 | 13 | 0 / 4 / 0.154 | 0.6 / 2.5 |
| V2 dense MiniLM | 0.659 | 0.765 / 0.854 / 0.357 | 11 | 0.370 | 0 / 6 / 0.077 | 0.653 | 13 | 0 / 4 / 0.154 | 10 / 1.9 |
| V3 hybrid (RRF) | 0.632 | 0.792 / 0.829 / 0.276 | 9 | 0.296 | 0 / 6 / 0.077 | 0.646 | 13 | 0 / 4 / 0.154 | 24 / 2.9 |
| V4 hybrid + ms-marco rerank | 0.591 | 0.788 / 0.812 / 0.172 | 8 | 0.185 | 0 / 6 / 0.077 | 0.663 | 12 | 0 / 4 / 0.154 | 65 / 2.7 |
| V5 V4 + graph expansion | 0.631 | 0.780 / 0.822 / 0.290 | 9 | 0.333 | 0 / 6 / 0.077 | 0.664 | 14 | 0 / 4 / 0.154 | 55 / 2.5 |
| **V6 V2, only when terms are not in the CV** | **0.665** | 0.768 / 0.854 / 0.373 | 9 | 0.407 | 0 / 6 / 0.077 | 0.644 | 13 | 0 / 4 / 0.154 | 9 / 2.0 |

\* V0 timing is from the T08b run, not the same session. V6 skipped the block on 31 dev + 36 test rows.
Alias-type T06 errors fixed (3 dev + 3 test rows): 0/6 for every variant except V4 (1/3 on dev).

**Choice (rule: dev macro-F1, then false rejects, then simpler): V6.** It is the only variant above V0 on dev, but the
margin is small: against V0 it fixes 10 dev rows and breaks 8 (net +2 of 182; a sign test gives p ≈ 0.8), and on test
it is lower (0.644 vs 0.661: 3 fixed, 6 broken). The gate does not move at all: false invites 0, false rejects and
review rate identical for all seven variants. Honest reading: **better retrieval (dev MRR 0.44 -> 0.76 on the drafted golds, 0.52 -> 0.80 on the checked ones) does not translate
into a measurable Matcher gain on 364 rows.** Why:
- the Matcher's errors are mostly about the CV (vague or missing evidence, years, "hands-on"), not about vocabulary; the
  six alias rows stay wrong with the dense refs too (knowledge says what a term means, it cannot make a buried term a
  quote);
- changing the knowledge block shifts the label probabilities a little, and the confidence rule (tau_conf 0.72) turns
  near-threshold answers MISSING <-> UNCERTAIN: on dev V2 vs V0 changes 17 final decisions but only 6 raw model
  decisions. Most of the spread between variants is this flip, i.e. noise around the threshold;
- the LoRA was trained with BM25 knowledge (V2 p1 format); dense refs are a small distribution shift.
What V6 does give: no knowledge block when it is not needed (18% of rows), a cheaper and faster dense lookup than the
hybrid/rerank variants, and a retriever that finds the right concept when a requirement uses another name.
