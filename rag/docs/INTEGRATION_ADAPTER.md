# Integration adapter proposal for Dali's backend (draft)

Status: **proposal; Dali's schemas are not yet in the repository.** The user reported that Dali delivered
pipeline schema v0.2.0 and RAG search schema v1.1.0, but neither file is in `semahayachi/HireSignal-5DS` or
in this build environment. The field mapping in section 3 therefore cannot be filled in yet, and no adapter
code has been written against a guessed schema.

## 1. Principle

The retrieval core (`retrieval.Retriever.search`) and the evaluated configuration (structure chunking,
e5-small, dense) do not change. The only new code is a translation layer:

```
Dali backend --(RAG search schema v1.1.0 request)--> POST /v1/search  (new, rag/adapter.py)
     adapter: validate request -> map to search(query, k, mode, filters) -> map result to v1.1.0 response
existing:  POST /retrieve (schema 0.1-provisional) stays as is for n8n and the evaluation tests
```

- One file, `rag/adapter.py`: Pydantic models generated from Dali's JSON Schema
  (`datamodel-codegen --input rag_search_v1.1.0.json --input-file-type jsonschema`), plus two mapping
  functions `to_search_args(request)` and `to_response(query, search_output)`.
- One route added to `api.py`, reusing the already-loaded `retriever`. No second model, no second index.
- Contract tests: each example in Dali's schema (and any examples he provides) is sent to the route, and the
  response is validated against his JSON Schema with `jsonschema`. Mismatch = failing test, not silent drift.
- The response always carries `schema_version: "1.1.0"` exactly as his schema defines it.

## 2. What our side guarantees (independent of his field names)

| Guarantee | Source in our response today |
|---|---|
| Evidence text and exact location in the posting | `text`, `char_span`, `section`, `chunk_id` |
| Traceable source | `source_type`, `source_id` (USAJOBS id or ESCO URI), `url`, `title` |
| Honest scores | `relevance_score` = cosine (dense), BM25 or RRF; never a probability or candidate-fit score |
| No forced answer | `status: no_match` with empty results when nothing is retrieved |
| No personal data | queries are skill mentions / requirement questions only; CV text must not be sent |

## 3. Field mapping (to fill in from Dali's schema v1.1.0)

| Dali request field | Our parameter | Notes |
|---|---|---|
| ? (query text) | `query` | 1–500 chars |
| ? (job identifier) | `filters.job_id` | must match our `job_id` values (e.g. `usajobs-882803700`) or a lookup table is needed |
| ? (collection / source filter) | `filters.source_type` | `job` / `esco` |
| ? (top-k) | `top_k` | 1–20, default 5 |

| Our response field | Dali response field | Notes |
|---|---|---|
| `status` | ? | `found` / `no_match` |
| `results[].text`, `char_span`, `section` | ? | evidence |
| `results[].source_id`, `url`, `title` | ? | citation |
| `results[].relevance_score` | ? | must not be relabelled as confidence |

Questions for Dali, to answer from his schema:
1. How does the pipeline (v0.2.0) identify a job: our `job_id`, or his own id needing a mapping table?
2. Does his search request carry one query or a batch (one per requirement)? A batch maps to a loop over `search`.
3. Which fields are required in his response, and is a `no_match` / empty-results state defined?
4. Does any field expect a probability or confidence? If so we must discuss it: our scores are not calibrated.

## 4. Effort once the schemas are in the repo

About 1–2 hours: generate models, write the two mapping functions and one route, add contract tests,
then run the n8n workflow against the new route. Nothing in `retrieval.py`, `chunking.py` or the
evaluation changes.
