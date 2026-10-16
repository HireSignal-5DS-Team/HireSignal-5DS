# RAG API contract — PROVISIONAL (schema_version 0.1-provisional)

Status: proposed to the backend owner (Dali), **not confirmed**. The retrieval core (`retrieval.py`) does not
depend on this schema; only `api.py` does, so changes here are cheap.

## Request: `POST /retrieve`

```json
{"query": "must-have requirements", "top_k": 5,
 "filters": {"job_id": "usajobs-812345600", "source_type": "job"},
 "mode": "hybrid"}
```
- `query`: 1–500 characters. Skill mentions or requirement questions. **Never send CV text or personal data.**
- `filters.job_id`: restrict to one posting. `filters.source_type`: `job` or `esco`.
- `mode`: optional, `bm25` | `dense` | `hybrid`; default `dense` when a dense model is loaded (best on the ESCO evaluation), else `bm25`.

## Response

```json
{"schema_version": "0.1-provisional", "query": "...", "filters": {...},
 "status": "found | no_match",
 "retrieval": {"mode": "hybrid", "chunking": "structure", "model": "intfloat/multilingual-e5-small"},
 "best_dense_score": 0.83,
 "results": [{"rank": 1, "source_type": "job", "source_id": "usajobs-812345600",
              "chunk_id": "usajobs-812345600#structure-3", "title": "Data Scientist",
              "section": "Qualifications", "url": "https://...", "char_span": [1520, 2210],
              "text": "...", "relevance_score": 0.0325}],
 "note": "relevance_score ranks text similarity only; it is not a probability and not candidate fit."}
```
- `status = no_match` → `results` is empty. Currently returned only when nothing is retrieved: a cosine
  threshold was tested and did not separate answerable from unanswerable queries (see EVALUATION.md); the Matcher must mark the requirement "uncertain", never invent evidence.
- `char_span` points into the original posting text, so the report can quote the exact evidence.
- `relevance_score` is BM25, cosine or RRF depending on `mode`. Do not threshold or average it downstream.

`GET /health` returns strategy, model and chunk count.

## Additional endpoints (2026-10-15)

- `POST /knowledge` — same request and retrieval as `/retrieve`; returns `{"status", "knowledge_refs": [...]}` where
  each item is the Qwen3-4B Matcher's `KnowledgeRef` (`rag/contracts/KnowledgeRef.schema.json`, copied verbatim from
  the Matcher branch; validated in tests). `retrieval` names the retriever, e.g. `rag.dense.e5-small`.
- `POST /mock/v1/search` — **mock** for Dali's backend: `schema_version: "mock-0 ..."`. Dali's `pipeline` v0.2.0 and
  `rag_search` v1.1.0 schemas are not in the repository; no field of theirs has been guessed.
- `GET /health` — now also reports `profile`, `index` (collection name) and `index_reused` (true after a restart).
- Profiles: start the API with `RAG_PROFILE=baseline` (default/fallback), `async-experimental` or
  `baseline-abstain-experimental` (see `profiles.py`). The response schema does not change between profiles.
