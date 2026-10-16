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
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from integration.contract import CONTRACT_VERSION, validate_output
from matcher.schemas import CV, Job

MATCH_SEMAPHORE = asyncio.Semaphore(1)
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
    return out
