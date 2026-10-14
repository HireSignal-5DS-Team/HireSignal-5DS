# HireSignal RAG component

Retrieves traceable evidence for the Matcher agent from two collections:
**job postings** (what a specific employer requires) and **ESCO skills** (what a skill term means, its synonyms).
CVs are never indexed and no personal data is sent to retrieval.

```
query (+ filters job_id / source_type)
   ├─ BM25 (bm25s) ───────────────┐
   └─ dense (e5 / bge-m3, Qdrant) ┴─ RRF fusion ─ top-5 ─ abstain if best cosine < tau ─ evidence JSON
```

| File | Role |
|---|---|
| `build_esco.py` | Builds the ESCO ICT/data subset from a pinned, hash-checked mirror; writes `docs/esco_coverage.md` |
| `corpus.py` | Loads postings (provenance header required) and ESCO entries |
| `chunking.py` | S1 fixed-size and S2 structure-aware chunking, with character offsets |
| `retrieval.py` | BM25, dense (Qdrant local mode), RRF, filters, abstention |
| `evaluate.py` | Known-answer evaluation grid → `eval/results/summary.md` |
| `api.py` | FastAPI `POST /retrieve` (provisional contract, `docs/API_CONTRACT.md`) |
| `n8n/hiresignal_rag_workflow.json` | n8n workflow: Manual/Webhook trigger → RAG → evidence for the Matcher |
| `docs/` | Sources and rights, decision log with failed attempts, coverage, API contract |

## Run

```bash
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r rag/requirements.txt
python rag/build_esco.py                              # needs git + github.com; reproduces data/esco/*.jsonl
python -m pytest -q rag/tests
python rag/evaluate.py                                # BM25 only
python rag/evaluate.py --models e5-small bge-m3       # dense + hybrid; needs huggingface.co
RAG_PROFILE=baseline uvicorn api:app --app-dir rag --port 8000   # profiles: see profiles.py
```

On the shared laptop, force CPU so the LLM benchmark keeps the GPU:
`CUDA_VISIBLE_DEVICES=` (PowerShell: `$env:CUDA_VISIBLE_DEVICES=""`).

n8n: import `n8n/hiresignal_rag_workflow.json`. If n8n runs in Docker, change the HTTP node URL from
`http://localhost:8000` to `http://host.docker.internal:8000`.
