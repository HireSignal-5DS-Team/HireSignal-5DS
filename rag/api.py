"""HTTP retrieval service for the Matcher agent and the n8n workflow.

Run: RAG_STRATEGY=structure RAG_MODEL=e5-small HF_HOME=<cache> uvicorn api:app --app-dir rag --port 8000
Without RAG_MODEL the service runs BM25-only (no model download, no abstention).
The JSON schema is PROVISIONAL until confirmed with the backend owner (see docs/API_CONTRACT.md).
"""
import os
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

from corpus import build_chunks
from retrieval import MODELS, Retriever

SCHEMA_VERSION = "0.1-provisional"
STRATEGY = os.environ.get("RAG_STRATEGY", "structure")
MODEL = os.environ.get("RAG_MODEL") or None
retriever = Retriever(build_chunks(STRATEGY), model=MODEL,
                      store_path=os.path.join(os.path.dirname(__file__), "index") if MODEL else None)
app = FastAPI(title="HireSignal RAG", version=SCHEMA_VERSION)


class Filters(BaseModel):
    job_id: str | None = None
    source_type: Literal["job", "esco"] | None = None


class Query(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(5, ge=1, le=20)
    filters: Filters = Filters()
    mode: Literal["bm25", "dense", "hybrid"] | None = None


@app.get("/health")
def health():
    return {"status": "ok", "strategy": STRATEGY, "model": MODEL, "chunks": len(retriever.chunks)}


@app.post("/retrieve")
def retrieve(q: Query):
    # dense won on the ESCO evaluation (eval/results/summary.md); revisit once job postings are evaluated
    mode = q.mode or ("dense" if MODEL else "bm25")
    filters = {k: v for k, v in {"doc_id": q.filters.job_id, "source_type": q.filters.source_type}.items() if v}
    out = retriever.search(q.query, k=q.top_k, mode=mode, filters=filters)
    return {
        "schema_version": SCHEMA_VERSION, "query": q.query, "filters": q.filters.model_dump(exclude_none=True),
        "status": out["status"], "retrieval": {"mode": mode, "chunking": STRATEGY, "model": MODEL and MODELS[MODEL][0]},
        "best_dense_score": out["best_dense_score"],
        "results": [{
            "rank": i, "source_type": c["source_type"], "source_id": c["doc_id"], "chunk_id": c["chunk_id"],
            "title": c["title"], "section": c["section"], "url": c["url"], "char_span": [c["start"], c["end"]],
            "text": c["text"], "relevance_score": round(s, 4),
        } for i, (c, s) in enumerate(out["results"], 1)],
        "note": "relevance_score ranks text similarity only; it is not a probability and not candidate fit.",
    }
