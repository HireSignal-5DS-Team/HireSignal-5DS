# HireSignal RAG component — final report (2026-10-14)

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

## 5. Matcher integration

- `POST /retrieve` (FastAPI, schema `0.1-provisional`): returns status, source type, source ID, URL, section,
  character span, text and relevance score (labelled as not a probability).
- n8n workflow (`n8n/hiresignal_rag_workflow.json`) tested end-to-end via manual and webhook triggers.
- Adapter for the backend schemas (pipeline v0.2.0, RAG search v1.1.0): **blocked**, schema files not yet in the
  repository; design in `INTEGRATION_ADAPTER.md`.

## 6. Limitations

- Small benchmark (42 reviewed queries): differences of 1–3 hits are not significant.
- Labels: AI-drafted, then AI-assisted review approved by one person; no inter-annotator agreement.
- Postings are US federal announcements (long, administrative, coarse headings); the must-have vs nice-to-have
  chunking hypothesis could not be tested on them.
- ESCO v1.1.x, not v1.2.1; tool-level skills missing from ESCO.
- No abstention: the Matcher must check that a retrieved ESCO label actually names the skill.
- Latency measured on a 4-core cloud CPU, not the demo laptop.

## 7. Reproduce

```bash
pip install -r rag/requirements.txt
python rag/build_esco.py && python rag/build_jobs.py          # rebuild both collections from pinned sources
python -m pytest -q rag/tests
HF_HOME=<cache> CUDA_VISIBLE_DEVICES= python rag/verify_index.py
HF_HOME=<cache> CUDA_VISIBLE_DEVICES= python rag/evaluate.py --models e5-small bge-m3                  # original labels
python rag/review.py apply --sheet rag/eval/review/decisions_ai_assisted_2026-10-14.csv \
  --reviewer "..." --provenance "user-approved AI-assisted review (not independent human annotation)"
HF_HOME=<cache> CUDA_VISIBLE_DEVICES= python rag/evaluate.py --queries rag/eval/queries_reviewed.jsonl --models e5-small bge-m3
python rag/compare_results.py
RAG_MODEL=e5-small uvicorn api:app --app-dir rag --port 8000
```
