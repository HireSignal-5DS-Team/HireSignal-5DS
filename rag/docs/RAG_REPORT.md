# HireSignal RAG component — final report (updated 2026-10-15)

## 0. Final architecture (summary)

| Component | Final choice | Evidence |
|---|---|---|
| Knowledge base | 20 USAJOBS postings (public domain) + 1,621 ESCO ICT/data skills (CC BY 4.0), hash-pinned builds | section 2, `SOURCES.md` |
| Chunking | structure-aware, 300-word sections with `Job / Section` header; ESCO one entry = one chunk | exp01–03 |
| Embedding | `intfloat/multilingual-e5-small`, CPU, loaded once in the API process | exp02–03 |
| Index | Qdrant local mode on disk (`rag/index/`), built once by `build_index.py`, reused after restarts | `MODEL_EXECUTION.md`, `RUNTIME.md` |
| Retrieval | dense, exact cosine, top-k 5, **job-ID filter mandatory** for job-specific queries | exp02–03 |
| Reranking / abstention | not in the default; available as opt-in experimental profiles | exp03 |
| Interfaces | `/retrieve` (provisional), `/knowledge` (Matcher `KnowledgeRef`), `/mock/v1/search` (mock for Dali), n8n workflow | section 5 |

Measured on the dev set (42 reviewed queries): ESCO + job-filtered MRR 0.865, Hit@1 31/40; p95 latency ≤ 164 ms
per query on a 4-core CPU; ~1.3 GB RAM. No generalisation claim yet: the sealed final test awaits review (section 7).


Branch `claude/gracious-fermi-ncuem4`. Details: `SOURCES.md`, `DECISIONS.md` (decisions and 22 logged
failures/corrections), `EVALUATION.md` (all results), `INDEX_VERIFICATION.md`, `../eval/review/VALIDATION.md`.

## 1. Role in HireSignal

The Matcher asks the RAG for evidence: what a specific employer requires (job postings) and what a skill term
means (ESCO). The RAG returns traceable passages; it never scores candidates. CVs are never indexed and no
personal data is sent to retrieval.

## 2. Knowledge base (collection and cleaning)

| Collection | Source | Size | Rights |
|---|---|---|---|
| ESCO skills | ESCO v1.1.x (en), European Commission, via the hash-pinned Tabiya GitHub mirror | 1,621 of 13,896 concepts: skills of 110 ICT/data occupations (ISCO 25, 35, 212, 1330) + 440 transversal skills | CC BY 4.0 |
| Job postings | 20 USAJOBS announcements (Sept 2026), via the hash-pinned CC0 Hugging Face dataset `abigailhaddad/usajobs-scraping` | 36,000 words; data scientists, AI/ML and AI software engineers, statisticians, IT specialists | public domain (US federal works) |

Cleaning: ESCO entries = label + alternative labels + description. Postings = the page's own sections verbatim
(Summary, Duties, Conditions of employment, Qualifications, Education, Additional information); logistics sections
dropped; e-mails and phone numbers replaced. Both builds are reproducible (`build_esco.py`, `build_jobs.py`).
ESCO coverage was measured: 29 of 38 frequent data/tech terms present; tool names such as PyTorch, Docker,
Power BI are absent from ESCO itself.

## 3. Chunking, embeddings, indexing, retrieval

- ESCO: one concept = one chunk (atomic entries).
- Postings: two strategies compared. S1 fixed 200 words / 30 overlap (218 chunks); S2 structure-aware: page
  headings, `Job | Section` prefix, long sections split at sentence boundaries (197 chunks). Chosen: **S2**.
- Embeddings: `intfloat/multilingual-e5-small` (chosen) vs `BAAI/bge-m3`; CPU inference.
- Index: Qdrant local mode (on-disk, payload filters) + BM25 (`bm25s`); RRF fusion available.
- Retrieval: dense, top-k 5, filters `job_id` / `source_type`. No cosine threshold (tested, did not beat
  "always answer"); `no_match` only when nothing is retrieved.
- Verified: the served index holds all 1,818 chunks (197 job + 1,621 ESCO) covering all 1,641 source documents,
  with full character coverage of every posting (16/16 checks, `verify_index.py`).

## 4. Evaluation

Known-answer benchmark: 43 queries (14 ESCO, 25 job, 4 no-answer; 7 in French). Gold evidence = ESCO URI or
verbatim posting quote resolved to a character span, so both chunking strategies are scored on the same evidence.
Grid: 2 chunkings × {BM25, e5-small, bge-m3} × {dense, hybrid}; metrics Hit@1/5/10 (= Recall@k), MRR@10,
nDCG@10, latency; paired exact McNemar tests.

Human feedback: the 43 drafted queries went through an **AI-assisted review approved by the project owner**
(31 accept, 11 correct, 1 reject). Every correction was checked against the sources; corrections without a
supplied gold were not invented (J04, J10 flagged). This is not independent human annotation.

Default configuration (structure, e5-small, dense), reviewed labels:

| Collection | n | Hit@1 | Hit@5 | MRR@10 | nDCG@10 |
|---|---|---|---|---|---|
| ESCO | 16 | 11 | 15 | 0.786 | 0.825 |
| Jobs, scoped (how the Matcher calls it) | 24 | 20 | 24 | 0.917 | 0.938 |
| Jobs, global (all 20 postings) | 24 | 10 | 16 | 0.527 | 0.589 |
| No-answer | 2 | 0 correct `no_match` | | | |

Main findings: dense beats BM25 on ESCO and French queries; structure-aware chunking helps dense models
(bge-m3, all postings: 6 queries only structure gets right vs 1 only fixed, p = 0.13; not significant at 0.05); bge-m3 is not clearly
better than e5-small and is ~2.5x slower; hybrid has no uniform benefit; no cosine threshold separates
answerable from unanswerable queries.

## 4b. Extended benchmark (experiment 02)

Full report: `../experiments/exp02_benchmark/REPORT.md`; pre-registration (`PLAN.md`) and a 30-query holdout
were committed before any run; selection was frozen before the holdout was evaluated once.

- Tested: 7 chunkers (fixed, structure, recursive, semantic, sliding window, sentence, parent-child), 2 lexical
  retrievers (BM25, TF-IDF), 4 embedding models (e5-small, all-MiniLM-L6-v2, e5-base, BGE-M3), 2 RRF fusions and
  1 cross-encoder reranker (bge-reranker-v2-m3), one variable changed at a time, on the reviewed 42-query dev set.
- No candidate met the pre-registered rule (significant gain on ESCO + job-filtered queries, ≤ 300 ms median,
  no extra service): **structure + e5-small dense remains the production configuration.**
- Strongest quality option: e5-small → cross-encoder reranker (dev Matcher MRR 0.929 vs 0.865, holdout 0.910 vs
  0.803, holdout CI of the difference excludes 0) at ~9 s/query on CPU, so it is recorded as the first upgrade
  if a GPU or offline batching is available, not adopted.
- Parent-child chunking and e5-base are slightly better than the baseline on dev (n.s.); MiniLM, BM25 and TF-IDF
  are clearly worse on the Matcher settings; RRF fusion does not help.
- On the holdout the baseline reaches Matcher MRR 0.803 (ESCO 8/10, job-filtered 9/16 Hit@1): the dev numbers in
  section 4 are optimistic.

## 4c. Optimisation study (experiment 03)

Full report: `../experiments/exp03_optimization/REPORT.md`; audit `AUDIT.md`; pre-registered budgets and rule
`PLAN.md`. 27 configurations on dev (erratum 2026-10-15: earlier text said 28) (chunk sizes, parent-child variants, e5-base, three rerankers at top-5/10/20,
int8 quantisation, combinations), repeated latency for 13 finalists, calibrated abstention on a separate split.

- Two product profiles were defined before running: real-time (p95 ≤ 300 ms) and async Matcher evidence
  (p95 ≤ 2 s per query, ≤ 30 s per screening). Under both, **no candidate was significantly better than the
  baseline**, so **structure + e5-small dense remains the production configuration** for both.
- Best in-budget candidates: parent-child (3-sentence children) + e5-small, real-time (+0.037 MRR, n.s.);
  parent-child + e5-base + mmarco reranker, async (+0.048, n.s., 6x latency). The bge reranker is the strongest
  (+0.065, n.s. on Matcher; large gains on all-jobs search) but takes 3.5–10 s per query on CPU.
- Abstention: calibrated thresholds work on the calibration split (CV accuracy 0.85–0.95) but wrongly abstain on
  8/40 natural dev queries, so abstention stays opt-in until recalibrated on natural, human-reviewed queries.
- A fresh 36-query final test set is sealed and awaits human review; no generalisation claim is made before it.

## 5. Matcher integration

- Profiles (`profiles.py`, env `RAG_PROFILE`): `baseline` (selected, default and fallback), `async-experimental`
  (parent-child + e5-base + mmarco reranker), `baseline-abstain-experimental` (calibrated abstention). Same response schema.
- `POST /retrieve` (FastAPI, schema `0.1-provisional`): returns status, source type, source ID, URL, section,
  character span, text and relevance score (labelled as not a probability).
- `POST /knowledge`: the same retrieval returned as the Qwen3-4B Matcher's `KnowledgeRef` objects; the schema is a
  verbatim copy from the Matcher branch (`contracts/`) and the output is validated against it in tests. The Matcher's
  current in-process BM25 call of `Retriever` is covered by a compatibility test.
- n8n workflow (`n8n/hiresignal_rag_workflow.json`) tested end-to-end via manual and webhook triggers.
- Dali's backend schemas (pipeline v0.2.0, RAG search v1.1.0): **not in the repository**; `/mock/v1/search` is a
  labelled mock and `INTEGRATION_ADAPTER.md` describes the real adapter. No schema field has been guessed.
- Runtime: one process, no model server; embeddings precomputed and reused (`MODEL_EXECUTION.md`).
- End-to-end effect (audit, `audit/COMPLETE_RAG_AUDIT.md` §11): on 202 bench-v1 validation requirements, base Qwen3-4B
  Q4 macro-F1 was 0.649 without RAG, 0.608 with BM25 knowledge and 0.599 with dense knowledge (same server; neither
  difference significant, both negative). Longer prompts caused more invalid JSON. Recommendation: no RAG injection
  in the Matcher by default until a shorter, relevance-filtered format is re-tested.

## 6. Limitations

- Small benchmark (42 reviewed queries): differences of 1–3 hits are not significant.
- Labels: AI-drafted, then AI-assisted review approved by one person; no inter-annotator agreement.
- Postings are US federal announcements (long, administrative, coarse headings); the must-have vs nice-to-have
  chunking hypothesis could not be tested on them.
- ESCO v1.1.x, not v1.2.1; tool-level skills missing from ESCO.
- No abstention: the Matcher must check that a retrieved ESCO label actually names the skill.
- Latency measured on a 4-core cloud CPU, not the demo laptop.
- Holdout (exp02) written by Claude, not human-annotated, and since inspected; exp03 final test set unreviewed.
- Abstention thresholds from a template calibration split do not transfer to natural queries.
- No GPU measurements (no GPU available to this work).

## 7. Final test status and remaining dependencies

- Sealed final test set (`experiments/exp03_optimization/final_test_queries.jsonl`, 36 queries, SHA256 `0a14b0cd…`):
  **not evaluated**. Its review sheet in the repository has 36 undecided rows; `check_final_review.py` validates a
  filled sheet without running retrieval. Evaluation runs only after the review is approved.
- The planned review is AI-assisted with human approval; it must be reported as such, not as independent human annotation.
- Remaining dependencies: (1) approved final-test review; (2) Dali's two schema files; (3) natural-query calibration
  before abstention can be enabled; (4) GPU measurements, if a GPU is to be used.

## 8. Reproduce

```bash
pip install -r rag/requirements.txt
python rag/build_esco.py && python rag/build_jobs.py          # rebuild both collections from pinned sources
python -m pytest -q rag/tests                                   # + RAG_REAL=1 for real-model regression/performance tests
HF_HOME=<cache> CUDA_VISIBLE_DEVICES= python rag/verify_index.py
HF_HOME=<cache> CUDA_VISIBLE_DEVICES= python rag/evaluate.py --models e5-small bge-m3                  # original labels
python rag/review.py apply --sheet rag/eval/review/decisions_ai_assisted_2026-10-14.csv \
  --reviewer "..." --provenance "user-approved AI-assisted review (not independent human annotation)"
HF_HOME=<cache> CUDA_VISIBLE_DEVICES= python rag/evaluate.py --queries rag/eval/queries_reviewed.jsonl --models e5-small bge-m3
python rag/compare_results.py
cd rag/experiments/exp02_benchmark && python run.py dev && python analyze.py dev && python run.py holdout && python analyze.py holdout
cd rag/experiments/exp03_optimization && python run.py dev && python analyze.py dev && python run.py calibration && python analyze.py calibration && python latency.py && python analyze.py select
python rag/build_index.py --profile baseline --prune
RAG_PROFILE=baseline uvicorn api:app --app-dir rag --port 8000
python rag/runtime_check.py
```
