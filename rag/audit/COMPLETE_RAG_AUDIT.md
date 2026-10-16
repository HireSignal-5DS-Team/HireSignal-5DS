# HireSignal RAG — complete scientific audit (2026-10-15)

Branch `claude/gracious-fermi-ncuem4`. Companion files: `EXPERIMENT_COMPARISON.md` (method-by-method tables),
`EXPERIMENT_MATRIX.md` (all 58 measured configuration rows), `TEST_COVERAGE.md`, `REMAINING_GAPS.md`,
`FINAL_TEST_REVIEW_STATUS.md`, `chunking_examples.md`, `recompute_checks.md`. Every retrieval number in this audit was
**recomputed from the stored per-query results** (`recompute.py`); status tags: **V** verified by recomputation,
**N** newly measured in this audit, **NT** not tested, **B** blocked.

## 1. Architecture and data sources (verified in code and on disk)

| Item | Value | Status |
|---|---|---|
| Job postings | 20 real USAJOBS announcements (Sept 2026; public domain; via CC0 HF dataset `abigailhaddad/usajobs-scraping` rev `9f20234`, file SHA256-pinned); 36,000 words, 756–3,057 per posting | V |
| ESCO | 1,621 of 13,896 ESCO v1.1.x (en) skills (ICT/data occupations + transversal), Tabiya GitHub mirror commit `eb3e5f4`, CC BY 4.0, hash-pinned | V |
| Indexed units | 197 job chunks + 1,621 ESCO entries = 1,818 vectors; 1,641 source documents; 100% character coverage of every posting (`verify_index.py`, 16/16 checks) | V |
| Chunking | structure-aware: page headings, `Job: <title> | Section: <heading>` header, sections > 300 words split at sentence boundaries; ESCO = 1 entry per chunk | V |
| Embedding | `intfloat/multilingual-e5-small` (118 M params, 384-d), mean pooling, `query:`/`passage:` prefixes, L2-normalised (checked against `modules.json`) | V + N |
| Vector store | Qdrant local mode on disk (`rag/index/`, 7.2 MB), collection named by model + corpus fingerprint, built once (`build_index.py`), reused on restart | V |
| Retrieval | dense exact cosine, top-k 5, mandatory job-ID filter for job questions, `source_type` filter for ESCO; BM25 (`bm25s`) available as fallback | V |
| Not in default | reranking, hybrid RRF, abstention (opt-in experimental profiles) | V |
| Interfaces | `POST /retrieve` (provisional schema), `POST /knowledge` (Matcher `KnowledgeRef`, real schema), `POST /mock/v1/search` (mock for Dali), `GET /health`, n8n workflow; the Matcher also calls `Retriever` in-process in BM25 mode | V |

Query flow: requirement text → (optional profile) → e5-small query embedding (in-process) → Qdrant filtered exact
search → chunks with source ID, URL, section and character span → `/retrieve` JSON or Matcher `KnowledgeRef`.

Feature status: **implemented + tested**: everything in the table above, robustness behaviour (§12).
**Experimental (opt-in, off)**: parent-child + e5-base + mmarco profile, calibrated abstention profile.
**Missing**: Dali adapter (schemas absent), GPU path, unavailable-RAG handling on the Matcher side.

## 2. Corpus preparation

Verbatim page sections only (Summary, Duties, Conditions of employment, Qualifications, Education, Additional
information); application logistics dropped; e-mails/phones replaced (2 replacements). Known quirks kept: line breaks
lost in the scrape; 7 duplicated boilerplate chunks (2 shared across postings). ESCO entries: label + alternative labels
+ description; 0 duplicate texts or labels. Coverage probe: 29/38 frequent data/tech terms present; tool names such as
PyTorch, Docker, Power BI are absent from ESCO itself.

## 3–6. Chunking, embeddings, retrieval, reranking

Detailed tables in `EXPERIMENT_COMPARISON.md`. Summary (dev, Matcher setting = ESCO + job-filtered, n = 40):

| Question | Answer from the evidence |
|---|---|
| Best chunking | Parent-child 3-sentence children (MRR 0.902) > structure-300 (0.865, production) > semantic 0.860 ≈ fixed 0.858 ≈ sentence 0.856 > sliding/recursive 0.835 > structure-150 0.804. Only structure-150 differs from the baseline with a CI excluding 0 (worse), and only for one bootstrap seed. Structure-300 keeps multi-item requirement lists and section context together (real-posting example). |
| Best embedding | e5-base 0.897 (best French: 0.917 on 6 queries) vs e5-small 0.865 (n.s., +0.033 [−0.036, +0.102]) at 2.5x indexing time; BGE-M3 0.846; English-only MiniLM 0.732 (significantly worse, fails French: 0.517). |
| Best retrieval method | Dense (0.865) > TF-IDF (0.740) ≈ BM25 (0.730). BM25 matches exact job wording but misses ESCO synonyms (ESCO MRR 0.559 vs 0.786) and French (0.333 vs 0.750). |
| Does hybrid help? | No: BM25 + e5-small RRF 0.829, BM25 + BGE-M3 RRF 0.847; fusion lowers ESCO MRR. |
| Do rerankers justify their latency? | bge-reranker-v2-m3 top-20 reaches 0.929 (+0.065, CI [−0.010, +0.150], n.s. on dev; significant on the inspected exp02 holdout: +0.108 [+0.019, +0.210]) but costs ~5–10 s per query on this CPU; mmarco top-5 0.900 at p95 636 ms; English MiniLM reranker hurts French. Not justified for the CPU real-time path; candidate for async/GPU. |
| Best combination | No constructive stacking: parent-child + e5-base + bge@10 (0.925) ≤ bge@20 alone (0.929). |

## 7. Combination matrix

`EXPERIMENT_MATRIX.md` (58 rows: exp01 re-scored on reviewed labels, exp02, exp03), `EXPERIMENT_COMPARISON.md` §5–6.
Best quality: e5-small → bge@20 (0.929). Best latency: BM25 (0.2 ms). Best trade-off: parent-child 3-sentence +
e5-small (0.902, p95 132 ms). Best CPU-only ≤ 300 ms: structure + e5-small or pc@3s2 + e5-small (n.s. difference).
Best EN/FR balance: e5-base or any multilingual reranker. Best for the real Matcher: no injection (§11).

## 8. Experiments 01–03: reliability and reproducibility

| Check | Result | Status |
|---|---|---|
| Stored summaries vs per-query data | max |difference| of Matcher MRR = 0.0000 for all 21 exp02 and 27 exp03 configurations | N |
| Cross-experiment consistency | structure + e5-small dense = 0.865 in exp01 (production `Retriever` + Qdrant), exp02 and exp03 (numpy search); sliding 200/30 = 0.835 and BGE-M3 = 0.846 identical across exp01/exp02 | N |
| Reported claims of exp03 | MRR 0.865 / 0.902 / 0.912 / 0.929 and p95 128 / 132 / 1,058 ms reproduced from files; bge@20 ≈ 10 s is a single-shot median (no repeated p95) | V |
| Configuration count | exp03 ran **27** configurations (26 comparisons), not 28 as previously written — errata added | N (correction) |
| Pre-registration | plans, budgets, holdout/final-test files committed before the runs they govern (commits `22e5f13`, `7ed9824`, `8a766ec`) | V |

## 9. Metrics and statistical significance

Paired bootstrap 95% CIs (2,000 resamples) and exact McNemar tests on Hit@1, per comparison against the baseline.
exp03: 26 comparisons, smallest McNemar p = 0.219; **Holm-adjusted p = 1.0 for every comparison**; no positive CI
excludes 0 with seed 0 or seed 1. Small-sample warning: 40 Matcher queries (6 French); a +0.04 MRR effect is below
what this set can detect. Multiple-comparison risk: picking the max of 27 noisy estimates inflates its value (winner's
curse) — the reason the selection rule demanded significance. The exp02 holdout showed the baseline dropping from 0.865
(dev) to 0.803: dev numbers are optimistic. Precision@5 is not recoverable from stored data (N/A).

## 10. Latency, CPU, RAM, persistence (CPU only; no GPU available — no GPU numbers anywhere)

From `docs/RUNTIME.md` / `MODEL_EXECUTION.md` (Intel Xeon 2.1 GHz, 4 cores, 15 GB): cold build 46–54 s (190 s once
after a container reboot); restart 10–16 s with `index_reused: true` and identical results; RSS ~1.3 GB with e5-small
loaded (BM25-only 116 MB); query p95 ≤ 164 ms (embedding + search). exp03 latency: 20 queries × 5 repeats (3 for slow
configurations), warm models; single-shot timings are flagged as such. Latency was not re-measured during this audit
because the CPU was busy with Matcher runs (re-measuring would have produced contaminated numbers).

## 11. Matcher integration — does RAG improve Qwen3-4B?

Setup: the Matcher's own benchmark code (`claude/kind-albattani-k7qlt9` @ `a23f6b2`, unmodified, read-only checkout),
202 validation requirements (`bench-v1`, synthetic, split-disjoint; validation, not the locked test split),
Qwen3-4B-Instruct-2507 Q4_K_M GGUF (unsloth @ `a06e946`, SHA256 verified identical), temperature 0, 192 max tokens,
k = 3 ESCO references, prompt p1, CPU. A and B were run earlier by the Matcher session with `llama_cpp.server`; C and
the control reruns B′/A′ were run in this audit with `llama-server` (llama.cpp `620d222`, `-c 4096 -np 1 --jinja`).

Full table: `integration/results/matcher_comparison.md`. A = teammate no-RAG, B = teammate BM25 (`llama_cpp.server`);
A′, B′, C = this audit (`llama-server`, identical settings between them).

| Run | Knowledge | macro-F1 | JSON valid | UNCERTAIN rate | false-MET | latency p50/p95 s |
|---|---|---|---|---|---|---|
| A′ (control) | none | **0.649** | 0.931 | 0.475 | 0.009 | 10.6 / 15.4 |
| B′ | BM25 ESCO, k=3 | 0.608 | 0.866 | 0.515 | 0.009 | 13.2 / 18.3 |
| C | dense e5-small ESCO, k=3 | 0.599 | 0.876 | 0.520 | 0.009 | 16.4 / 23.5 |
| A (teammate) | none | 0.634 | 0.950 | 0.495 | 0.009 | 12.9 / 20.7 |
| B (teammate) | BM25 ESCO, k=3 | 0.630 | 0.916 | 0.505 | 0.009 | 16.4 / 34.2 |

Paired against A′ (same 202 requirements; McNemar on correctness, bootstrap 95% CI of macro-F1 difference):

| Comparison | Δ macro-F1 | 95% CI | McNemar p | alias acc. (n=21) | absent-skill acc. (n=11) | certification acc. (n=13) |
|---|---|---|---|---|---|---|
| B′ vs A′ | −0.041 | [−0.083, −0.000] | 0.093 | 0.29 → 0.43 | 0.45 → 0.36 | 0.54 → 0.23 |
| C vs A′ | −0.050 | [−0.101, +0.001] | 0.080 | 0.29 → 0.43 | 0.45 → 0.09 | 0.54 → 0.38 |
| C vs B′ | −0.009 | — | 0.851 | | | |
| A vs A′ (server drift) | −0.015 | [−0.045, +0.016] | 0.581 | | | |

JSON-failure analysis: unparsed outputs become UNCERTAIN (A′ 14, B′ 27, C 25 of 202). Mean prompt tokens 315 / 401 / 501
(A′ / B′ / C; dense always injects 3 references, BM25 injects none for 87/202). On the 167 requirements parsed in all
three runs, accuracy is 0.689 / 0.683 / 0.671 — nearly equal.

Interpretation: on bench-v1 validation, neither RAG variant improves the base Qwen3-4B Q4 Matcher; both point estimates
are lower (BM25 CI just touching 0, dense CI including 0, neither McNemar significant at 0.05). Most of the loss comes
from longer prompts causing more invalid JSON, not from worse decisions on parsed outputs. RAG helps skill aliases
(the case it was designed for) and hurts absent-skill traps and certifications, where related ESCO concepts push the
model toward MET/UNCERTAIN. Dense retrieval, better in retrieval metrics (§3–6), does not translate into better Matcher
decisions here. Limits: synthetic benchmark, one prompt (p1), one quantised model on CPU, base model only (no LoRA).

## 12. Robustness and security (14 new tests, `tests/test_robustness.py`)

Verified: malformed/empty/oversized/wrong-type requests → 422 on both routes; unknown job ID → `no_match`, never other
postings; the job filter never leaks other postings; duplicate indexing creates no duplicate vectors; a corpus change
re-embeds under a new fingerprint; 40 concurrent requests (8 threads) return the same results as sequential ones;
instruction-like text in a source is returned verbatim as data. **Actual failure found**: a corrupted index file
crashed startup (`DatabaseError`); fixed (moved aside + rebuilt) and tested. Remaining risks: the Matcher's resistance to
injected text was not tested end-to-end; untrusted sources are limited by provenance checks and hash pinning only;
unavailable-RAG handling does not exist on the Matcher side (no HTTP client yet); concurrency was tested on the BM25
API and with a stub embedder, not under real-model load. Unit tests passing do not prove the system secure.

## 13. API and Matcher contracts

`/knowledge` output validated against the Matcher's real `KnowledgeRef` JSON Schema (copied verbatim, provenance in
`contracts/README.md`); the Matcher's in-process BM25 call is covered by a compatibility test; Dali's
`pipeline.schema.json` v0.2.0 and `rag_search.schema.json` v1.1.0 are still absent from every branch (B) — only a
labelled mock route exists, no fields guessed. Interface is model-agnostic: the LoRA comparison is prepared in
`integration/README.md` (not run: adapter not delivered).

## 14. Test results in this audit

Unit tests (stub models): **30 passed**, 7 skipped (real-model tests). Real-model tests (`RAG_REAL=1`, e5-small /
e5-base / mmarco, CPU, offline cache): **7 passed** in 216 s, including the dev regression (Hit@1 ≥ 31/40), source
attribution, every profile from the persisted index and the p95 ≤ 300 ms budget. Run after llama-server was stopped.
One real defect was found and fixed during the audit (corrupted index crash, §12).

## 15. Final-test status

Not evaluated (B). The sealed set (36 queries) is intact (SHA256 verified); the review sheet in the repository and on
`claude/vigilant-albattani-dmn3pk` has 36 blank decisions; the AI-assisted review (24 accepted / 12 flagged) mentioned
by the owner is not present anywhere reachable. See `FINAL_TEST_REVIEW_STATUS.md`.

## 16. Limitations and remaining work

See `REMAINING_GAPS.md`. Main ones: no generalisation claim before the reviewed final test; 40 dev queries and 6 French
queries; abstention off; no GPU numbers; Dali schemas absent; LoRA comparison not run; Matcher-side injection and
outage handling untested.

## 17. Recommended production configuration

Retrieval service default (unchanged): **structure-aware chunking (300 words) + multilingual-e5-small dense, Qdrant
local persisted index, exact cosine, top-5, mandatory job filter, BM25 kept as fallback; no reranker, no fusion, no
abstention.** No alternative is significantly better after correction; e5-base and parent-child remain opt-in profiles;
rerankers only for an async/GPU path.

Matcher: **do not inject RAG knowledge by default** for the base Qwen3-4B Q4 Matcher — it lowered macro-F1 under
identical serving (§11). If RAG is kept, re-test a narrower variant before enabling it: inject only on
alias/terminology requirements, shorter knowledge text, a relevance cut-off (fewer than 3 references), and JSON-robust
decoding. Repeat the comparison with Dali's LoRA adapter under identical serving when it exists.
