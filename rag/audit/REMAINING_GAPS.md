# Remaining gaps before the RAG can be called complete (audit 2026-10-15)

| # | Gap | Why it matters | Owner / unblocker | Effort once unblocked |
|---|---|---|---|---|
| 1 | Sealed final test (36 queries) not evaluated; review sheet has 36 blank decisions; the mentioned AI-assisted review (24/12) is not in the repository | no generalisation claim is possible; all retrieval numbers are development-set numbers | project owner: complete/commit the review, run `check_final_review.py`, approve | ~15 min compute |
| 2 | Dali's `pipeline.schema.json` v0.2.0 and `rag_search.schema.json` v1.1.0 missing | real backend adapter cannot be written; `/mock/v1/search` is a placeholder | Dali | 1–2 h |
| 3 | Fine-tuned (LoRA) Matcher comparison | 4-way base/LoRA × RAG/no-RAG comparison prepared but not run | Dali (adapter) + a GPU or a GGUF conversion | ~4 runs × 1 h on CPU |
| 4 | Abstention (no-match) is off by default | calibrated thresholds wrongly abstained on 8/40 natural dev queries | natural, human-reviewed calibration queries | 1 h |
| 5 | French evaluation rests on 6 dev queries | multilingual claims are indicative only | more reviewed FR queries | — |
| 6 | Small dev set (40 Matcher queries, 27 configurations) | no candidate is significant after multiple-comparison correction | larger reviewed set | — |
| 7 | GPU latency never measured | reranker viability on GPU unknown | a GPU machine | 30 min |
| 8 | Matcher-side prompt-injection resistance not tested | RAG returns text verbatim; only the Matcher prompt labels it as terminology | Matcher owner / a targeted test with the real model | 1 h |
| 9 | Matcher uses BM25 in-process, not `/knowledge` | dense retrieval is better for ESCO and French in retrieval metrics; but end-to-end neither BM25 (−0.041) nor dense (−0.050) RAG improved Matcher macro-F1 (`COMPLETE_RAG_AUDIT.md` §11) | Matcher owner: shorter, relevance-filtered knowledge format, then re-test | ~3 h CPU per run |
| 10 | Unavailable-RAG handling on the Matcher side | no HTTP client exists yet, so timeouts/fallback are untested | Matcher owner | small |
| 11 | Precision@5 and contradictory-passage tests | gold data stores one first-hit rank; no contradiction labels | new annotation | — |
| 12 | GTE embeddings, MonoT5 reranker | never tested (only considered) | optional | 1–2 h each |
| 13 | 7 duplicated boilerplate job chunks (2 across postings) | harmless with the job filter; ambiguous in all-jobs search | optional de-duplication | small |
