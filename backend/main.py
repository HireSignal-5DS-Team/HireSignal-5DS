"""HireSignal FastAPI backend wrapping matcher.pipeline (contract v1.1.0).

Endpoints match frontend/INTEGRATION.md:
  GET  /health                  liveness
  GET  /ready                   models + RAG index + Matcher server reachable
  GET  /api/v1/models/status    pinned provenance + live /v1/models from the Matcher server
  POST /api/v1/match            {cv, job} -> PipelineOutput

Concurrency is bounded to 1 in-flight match (RTX 4050 budget).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from integration.contract import CONTRACT_VERSION, validate_output
from matcher.schemas import CV, Job

MATCH_SEMAPHORE = asyncio.Semaphore(1)
REPORTER_SEMAPHORE = asyncio.Semaphore(1)
_PIPELINE: dict[str, Any] = {"obj": None, "err": None}


def _build_pipeline():
    """Build the matcher pipeline once, cache. Called lazily (first /ready or /match)."""
    if _PIPELINE["obj"] is not None:
        return _PIPELINE["obj"]
    try:
        from matcher.factory import build
        _PIPELINE["obj"] = build(dict(os.environ))
        _PIPELINE["err"] = None
    except Exception as e:
        _PIPELINE["err"] = f"{type(e).__name__}: {e}"
        raise
    return _PIPELINE["obj"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(title="HireSignal", version=CONTRACT_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "hiresignal-backend",
        "contract_version": CONTRACT_VERSION,
    }


async def _probe_matcher_models() -> dict[str, Any]:
    url = os.environ.get("HS_MATCHER_URL", "http://127.0.0.1:8081/v1").rstrip("/")
    expected = os.environ.get("HS_MATCHER_MODEL", "Qwen/Qwen3-4B-Instruct-2507+lora")
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{url}/models")
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "url": url, "expected": expected}
    ids = [m.get("id") for m in data.get("data", [])]
    return {"ok": expected in ids, "url": url, "expected": expected, "served": ids}


@app.get("/ready")
async def ready():
    checks: dict[str, Any] = {}
    checks["matcher"] = await _probe_matcher_models()
    try:
        _build_pipeline()
        checks["pipeline"] = {"ok": True}
    except Exception as e:
        checks["pipeline"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    checks["rag_dir"] = {"ok": Path(os.environ.get("HIRESIGNAL_RAG_DIR", ROOT / "rag")).exists()}
    ok = all(c.get("ok") for c in checks.values())
    body = {"ready": ok, "checks": checks, "contract_version": CONTRACT_VERSION}
    return JSONResponse(body, status_code=200 if ok else 503)


@app.get("/api/v1/models/status")
async def models_status():
    cfg_path = ROOT / "config" / "matcher_models.json"
    try:
        pinned = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        pinned = {"error": f"{type(e).__name__}: {e}"}
    matcher_live = await _probe_matcher_models()
    judge_model = os.environ.get("HS_JUDGE_MODEL", "cross-encoder/nli-deberta-v3-xsmall")
    judge_rev = os.environ.get("HS_JUDGE_REVISION", "a150876415327c80daeff35ca6f68f5ed8cf5c24")
    rag_mode = os.environ.get("HS_RAG", "gated")
    reporter_slm = os.environ.get("HS_REPORTER_SLM", "on")
    reporter_path = os.environ.get("HS_REPORTER_MODEL_PATH")
    return {
        "pinned": pinned,
        "runtime": {
            "matcher": matcher_live,
            "judge": {"model": judge_model, "revision": judge_rev,
                      "enabled": os.environ.get("HS_JUDGE") != "off"},
            "rag": {"mode": rag_mode, "dir": str(ROOT / "rag")},
            "reporter": {"slm": reporter_slm, "model_path": reporter_path},
            "concurrency_limit": 1,
        },
        "contract_version": CONTRACT_VERSION,
    }


@app.get("/api/v1/rag/inspect")
async def rag_inspect(
    term: str = Query(min_length=1, max_length=120),
    category: Literal["skill", "experience", "education", "certification", "language", "other"] = "skill",
):
    """Read-only knowledge retrieval check: no CV data and no Matcher inference.

    Uses the SAME configured knowledge provider as /match. The query is a
    requirement term, never submitted candidate text. Serialized against
    active matching so shared retrieval trace metadata cannot be mixed up.
    """
    term = term.strip()
    if not term:
        raise HTTPException(status_code=422, detail="term must not be blank")
    from matcher.schemas import Requirement

    async with MATCH_SEMAPHORE:
        try:
            pipeline = _build_pipeline()
            knowledge = pipeline.matcher.knowledge
            req = Requirement(req_id="inspection", text=term, skill_terms=[term], category=category)
            t0 = time.perf_counter()
            def retrieve():
                refs = knowledge.lookup(req, k=3)
                # GatedKnowledge exposes the decision path for this lookup.
                trace = getattr(knowledge, "last_trace", None)
                return refs, trace
            loop = asyncio.get_running_loop()
            refs, trace = await loop.run_in_executor(None, retrieve)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"retrieval unavailable: {type(exc).__name__}")
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    return {
        "query": term,
        "category": category,
        "provider": getattr(knowledge, "name", type(knowledge).__name__),
        "corpus_esco": len(getattr(knowledge, "esco", {})) or None,
        "elapsed_ms": elapsed_ms,
        "retrieved": len(refs),
        "trace": trace,
        "references": [
            {
                "title": ref.title,
                "source_type": ref.source_type,
                "source_id": ref.source_id,
                "url": ref.url,
                "text": ref.text,
                "retrieval": ref.retrieval,
                "score": ref.relevance_score,
            }
            for ref in refs
        ],
        "meaning": "Knowledge helps interpret terms; it is NOT evidence of a candidate's skills.",
    }


@app.post("/api/v1/match")
async def match(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="request body must be JSON")
    if not isinstance(body, dict) or "cv" not in body or "job" not in body:
        raise HTTPException(status_code=400, detail="body must be {\"cv\": {...}, \"job\": {...}}")
    try:
        cv = CV.model_validate(body["cv"]).model_dump()
        job = Job.model_validate(body["job"]).model_dump()
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"schema validation failed: {e}")

    async with MATCH_SEMAPHORE:
        t0 = time.perf_counter()
        try:
            pipeline = _build_pipeline()
            loop = asyncio.get_running_loop()
            out = await loop.run_in_executor(None, pipeline.run, cv, job)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"pipeline failed: {type(e).__name__}: {e}")
        elapsed = time.perf_counter() - t0

    try:
        validate_output(out)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"pipeline produced invalid output: {e}")

    out.setdefault("_meta", {})["elapsed_s"] = round(elapsed, 2)
    # The existing matcher pipeline does not call the Report Writer itself.
    # Add the verified, grounded report as an optional presentation envelope.
    # Keep the Matcher contract unchanged and do not fabricate SLM success.
    try:
        from backend.reporter_adapter import render_report
        reporter_t0 = time.perf_counter()
        async with REPORTER_SEMAPHORE:
            loop = asyncio.get_running_loop()
            out["reporter"] = await loop.run_in_executor(
                None, render_report, out, job.get("title", "")
            )
        out["_meta"]["reporter_elapsed_s"] = round(time.perf_counter() - reporter_t0, 2)
    except Exception as exc:
        out["_meta"]["reporter_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return out
