# Test coverage (audit 2026-10-15)

Automated tests: `rag/tests/` — 30 unit tests (stub models, run by default) + 7 real-model tests (`RAG_REAL=1`,
download e5-small / e5-base / mmarco). Results of the audit run are in `COMPLETE_RAG_AUDIT.md` §14.
Retrieval-quality metrics come from the experiment scripts (dev set), not from unit tests.

## Retrieval quality

| Item | Where it is measured / tested | Status |
|---|---|---|
| Hit@1, Hit@5, Hit@10 | `recompute.py` (all experiments); `test_regression_dev_matcher_hit_at_1` (≥ 31/40 Hit@1, real model) | covered (dev set) |
| Recall@1, @3, @5 | `recompute.py` — equal to Hit@k because one relevant item is counted per query | covered (dev set) |
| Precision@5 | not recoverable: only the first gold rank is stored per query | **not measured** |
| MRR@10, nDCG@10 | `recompute.py`, experiment summaries | covered (dev set) |
| Correct source attribution | `test_source_attribution` (real), `test_parent_child_rerank_attribution_and_abstention`, exp03 attribution@1 column | covered |
| Exact evidence spans | `test_source_attribution`, `test_exp02_chunkers_preserve_source`, `test_production_parent_child_equals_experiment`, `verify_index.py` (100% character coverage) | covered |
| Job-ID filtering | `test_job_filter_never_leaks_other_postings`, `test_unknown_job_id_returns_no_match_not_other_jobs`, `test_source_attribution` | covered |
| ESCO skill retrieval | dev ESCO queries (16); `test_matcher_bm25_call_compatible`; `test_knowledge_refs_match_matcher_schema` | covered (dev set) |
| English and French | dev subsets EN (34) / FR (6) in `recomputed_metrics.csv` | covered, **FR sample very small** |
| Synonyms and paraphrases | dev queries (e.g. E04, E07, J03, J05); final test set has paraphrase/typo items (sealed) | partial |
| Rare technical skills | dev N01/N02 (Kubernetes, Power BI → broader ESCO concepts); ESCO coverage check | partial |
| Missing evidence / no-answer | dev N03/N04, calibration split (20 unsupported), `test_no_answer_with_abstention_profile` | partial: abstention off by default |
| Irrelevant documents | all-jobs setting shows wrong-posting retrieval; job filter prevents it in the Matcher setting | covered |
| Duplicate documents | audit: 0 duplicate ESCO texts/labels; 7 duplicated boilerplate job chunks (2 across postings) | measured, not tested |
| Contradictory retrieved passages | no contradiction labels exist in the corpus or queries | **not tested** |

## Robustness, security, runtime

| Item | Test / measurement | Status |
|---|---|---|
| Empty, too long, wrong-type, out-of-range, unknown-enum requests | `test_malformed_requests_rejected` (8 cases × 2 routes → HTTP 422) | covered |
| Invalid job ID | `test_unknown_job_id_returns_no_match_not_other_jobs` | covered |
| Unavailable RAG API | the Matcher calls the RAG in-process (BM25); no HTTP client exists yet on the Matcher side | **not tested** (no client to test) |
| Missing index | built on first start (`test_index_persists_across_restart`, `runtime_check.py` cold phase) | covered |
| Corrupted index | `test_corrupted_index_is_moved_aside_and_rebuilt` — **failed before the audit fix** (startup crashed) | fixed + covered |
| Duplicate indexing | `test_duplicate_indexing_and_corpus_update` (no duplicated vectors) | covered |
| Corpus update / reindexing | same test (new fingerprint → re-embedded) | covered |
| Application restart, index persistence | `test_index_persists_across_restart`; API restarted twice (`index_reused: true`) | covered |
| Model loading, memory, cold/warm latency | `runtime_check.py` → `docs/RUNTIME.md` | measured |
| Concurrent requests | `test_concurrent_requests_match_sequential` (40 requests, 8 threads, BM25 API); stub dense concurrency check | covered (not under real-model load) |
| Prompt injection in retrieved text | `test_injected_instructions_are_returned_verbatim_as_data` (RAG side only) | partial: the Matcher's resistance is not tested |
| Untrusted / misleading sources | provenance enforced at load (`test_missing_provenance_rejected`); sources pinned by hash | partial |
| Performance budget | `test_performance_p95_realtime_budget` (p95 ≤ 300 ms, real model) | covered |
| All profiles | `test_every_profile_serves_from_persisted_index[3 profiles]`, `test_profiles_are_valid` | covered |
| Matcher contract | `test_knowledge_refs_match_matcher_schema` (real Matcher `KnowledgeRef` schema), `test_matcher_bm25_call_compatible` | covered |
| Dali's contracts | schemas absent; only a mock route exists | **blocked** |
