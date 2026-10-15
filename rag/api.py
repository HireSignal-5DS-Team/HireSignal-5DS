"""HTTP retrieval service for the Matcher agent and the n8n workflow.

Run: RAG_STRATEGY=structure RAG_MODEL=e5-small HF_HOME=<cache> uvicorn api:app --app-dir rag --port 8000
Without RAG_MODEL the service runs BM25-only (no model download, no abstention).
The JSON schema is PROVISIONAL until confirmed with the backend owner (see docs/API_CONTRACT.md).
"""
import os
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

from adapters import mock_dali_search, to_knowledge_refs
from corpus import build_chunks
from profiles import PROFILES
from retrieval import MODELS, Retriever

SCHEMA_VERSION = "0.1-provisional"
PROFILE = os.environ.get("RAG_PROFILE")  # e.g. baseline; unset = legacy RAG_STRATEGY / RAG_MODEL variables
if PROFILE:
    _p = PROFILES[PROFILE]
    STRATEGY, MODEL = _p["strategy"], _p["model"]
    _extra = {"reranker": _p["reranker"], "top_n": _p["top_n"] or 10, "thresholds": _p["thresholds"]}
else:
    STRATEGY = os.environ.get("RAG_STRATEGY", "structure")
    MODEL = os.environ.get("RAG_MODEL") or None
    _extra = {}
retriever = Retriever(build_chunks(STRATEGY), model=MODEL,
                      store_path=os.path.join(os.path.dirname(__file__), "index") if MODEL else None, **_extra)
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
    return {"status": "ok", "profile": PROFILE, "strategy": STRATEGY, "model": MODEL, "chunks": len(retriever.chunks),
            "index": getattr(retriever, "collection", None), "index_reused": getattr(retriever, "index_reused", None)}


@app.post("/retrieve")
def retrieve(q: Query):
    # dense won on the ESCO evaluation (eval/results/summary.md); revisit once job postings are evaluated
    mode = q.mode or ("dense" if MODEL else "bm25")
    filters = {k: v for k, v in {"doc_id": q.filters.job_id, "source_type": q.filters.source_type}.items() if v}
    out = retriever.search(q.query, k=q.top_k, mode=mode, filters=filters)
    return {
        "schema_version": SCHEMA_VERSION, "query": q.query, "filters": q.filters.model_dump(exclude_none=True),
        "status": out["status"], "retrieval": {"mode": mode, "chunking": STRATEGY, "model": MODEL and MODELS[MODEL][0], "profile": PROFILE,
                      "reranker": retriever.reranker},
        "best_dense_score": out["best_dense_score"],
        "results": [{
            "rank": i, "source_type": c["source_type"], "source_id": c["doc_id"], "chunk_id": c["chunk_id"],
            "title": c["title"], "section": c["section"], "url": c["url"], "char_span": [c["start"], c["end"]],
            "text": c["text"], "relevance_score": round(s, 4),
        } for i, (c, s) in enumerate(out["results"], 1)],
        "note": "relevance_score ranks text similarity only; it is not a probability and not candidate fit.",
    }


def _retrieval_name(mode):
    return f"rag.{mode}" + (f".{MODEL}" if MODEL and mode != "bm25" else "") + (f">{retriever.reranker}" if retriever.reranker else "")


@app.post("/knowledge")
def knowledge(q: Query):
    """Same retrieval as /retrieve, returned as the Matcher's KnowledgeRef objects (contracts/KnowledgeRef.schema.json)."""
    mode = q.mode or ("dense" if MODEL else "bm25")
    filters = {k: v for k, v in {"doc_id": q.filters.job_id, "source_type": q.filters.source_type}.items() if v}
    out = retriever.search(q.query, k=q.top_k, mode=mode, filters=filters)
    return {"status": out["status"], "knowledge_refs": to_knowledge_refs(out["results"], _retrieval_name(mode))}


@app.post("/mock/v1/search")
def mock_search(q: Query):
    """MOCK adapter for Dali's backend until his schemas are committed; see adapters.py."""
    mode = q.mode or ("dense" if MODEL else "bm25")
    filters = {k: v for k, v in {"doc_id": q.filters.job_id, "source_type": q.filters.source_type}.items() if v}
    return mock_dali_search(q.query, q.filters.job_id, q.top_k, retriever.search(q.query, k=q.top_k, mode=mode, filters=filters),
                            _retrieval_name(mode))
