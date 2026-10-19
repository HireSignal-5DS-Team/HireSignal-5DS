"""T16: demo page support for the station API (a view only: no pipeline logic here).

- GET  /ui/            the page (ui/index.html, static, offline)
- POST /ui/run         forwards the upload to the n8n webhook, adding X-HireSignal-Token from .env ON THE SERVER;
                       returns the n8n reply unchanged. One run at a time (409 otherwise).
- GET  /ui/progress    live per-station progress of the current UI run (in memory, reset at each /ui/run)
- GET  /ui/last-result the last /ui/run reply (in memory; lets the page re-open it, e.g. for screenshots)

The progress middleware only READS the station responses (status + a one-line summary of counts and labels, never CV
text) and returns them byte for byte, so the existing contracts and n8n are unchanged. It records nothing unless a UI
run is in progress.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from services.config import ROOT, env

WEBHOOK = env("N8N_WEBHOOK_URL", "http://127.0.0.1:5678/webhook/hiresignal")
STAGES = {"/reader": "reader", "/profile": "profile", "/job": "job", "/rag/search": "rag", "/match": "match",
          "/judge": "judge", "/bias": "bias", "/outcome": "outcome", "/report": "report"}
MAX_UPLOAD = 10 * 1024 * 1024

router = APIRouter()
_lock = asyncio.Lock()
_state: dict = {"active": False}
_last: dict = {}


def _reset(total: int | None) -> None:
    _state.clear()
    _state.update({"active": True, "run_id": f"ui-{int(time.time())}", "started": time.time(), "finished": None,
                   "total_requirements": total, "card_given": total is not None, "error": None, "stages": {}})


def progress_snapshot() -> dict:
    now = time.time()
    out = {k: v for k, v in _state.items() if k != "stages"}
    out["stages"] = {}
    for name, s in _state.get("stages", {}).items():
        end = s["end"] or now
        out["stages"][name] = {**s, "elapsed_s": round(end - s["start"], 1)}
    if _state.get("started"):
        out["elapsed_s"] = round((_state["finished"] or now) - _state["started"], 1)
    return out


def _count(xs) -> int:
    return len(xs) if isinstance(xs, list) else 0


def summarise(stage: str, body: dict, request_json: dict | None) -> tuple[str, dict]:
    """One line of counts and labels for a station response (no CV text, no quotes), plus small extras."""
    extra: dict = {}
    if stage == "reader":
        routes = sorted(set(body.get("read_path") or []))
        line = f"{body.get('file_type')}, route {', '.join(routes) or '-'}"
        if any(r != "text" for r in routes):
            line += f" (mode {body.get('mode')})"
        if body.get("ocr_confidence") is not None:
            line += f", OCR confidence {body['ocr_confidence']:.0f}"
        extra = {"review": body.get("review_reasons") or []}
    elif stage == "profile":
        p = body.get("profile") or {}
        line = (f"anonymised; {_count(p.get('skills'))} skills, {_count(p.get('experience'))} jobs, "
                f"{_count(p.get('education'))} degree{'' if _count(p.get('education')) == 1 else 's'}")
        if body.get("bias_flags"):
            line += f"; {len(body['bias_flags'])} protected lines removed"
        if body.get("injection_removed"):
            line += f"; {len(body['injection_removed'])} injected sentences removed"
    elif stage == "job":
        reqs = (body.get("card") or {}).get("requirements") or []
        must = sum(r.get("kind") == "must" for r in reqs)
        line = f"{len(reqs)} requirements ({must} must, {len(reqs) - must} nice)"
        if _state.get("total_requirements") is None:
            _state["total_requirements"] = len(reqs)
    elif stage == "rag":
        rid = ((request_json or {}).get("requirement") or {}).get("req_id", "?")
        line = f"{rid}: skipped, terms already in the CV" if body.get("skipped") else \
            f"{rid}: {_count(body.get('knowledge_refs'))} ESCO refs"
    elif stage == "match":
        line = f"{body.get('req_id')}: {body.get('decision')}"
        extra = {"req_id": body.get("req_id")}
    elif stage == "judge":
        line = f"{body.get('req_id')}: Judge {(body.get('judge') or {}).get('verdict')}"
    elif stage == "bias":
        sw = body.get("swap") or {}
        if sw.get("ran"):
            line = f"swap test ran ({sw.get('counterfactual')}), identical input: " \
                   f"{'yes' if sw.get('identical_matcher_input') else 'no'}"
        else:
            line = f"swap test skipped ({sw.get('skipped') or 'not needed'})"
        if body.get("review_reasons"):
            line += "; FLIP -> review"
    elif stage == "outcome":
        line = f"{body.get('outcome')} (score {body.get('score')})"
    elif stage == "report":
        line = f"{'AI' if body.get('source') == 'llm' else 'template'} report, {body.get('attempts')} attempt(s)"
    else:
        line = ""
    return line, extra


def install(app: FastAPI) -> None:
    """Add the progress middleware, the /ui routes and the static page. Call once, after all station routes."""

    @app.middleware("http")
    async def ui_progress(request, call_next):
        stage = STAGES.get(request.url.path)
        if not (_state.get("active") and stage and request.method == "POST"):
            return await call_next(request)
        req_json = None
        if stage in ("rag", "match"):
            raw = await request.body()  # cached by Starlette, the endpoint still reads it
            try:
                req_json = json.loads(raw)
            except ValueError:
                req_json = None
        s = _state["stages"].setdefault(stage, {"status": "running", "start": time.time(), "end": None,
                                               "summary": "", "calls": 0, "done": 0, "errors": 0})
        s.update(status="running", end=None)
        s["calls"] += 1
        response = await call_next(request)
        body = b"".join([chunk async for chunk in response.body_iterator])
        s["end"] = time.time()
        if response.status_code >= 400:
            s["errors"] += 1
            s["status"] = "error"
            s["summary"] = f"HTTP {response.status_code}"
        else:
            s["done"] += 1
            s["status"] = "done"
            try:
                s["summary"], extra = summarise(stage, json.loads(body), req_json)
                s.update(extra)
            except (ValueError, TypeError, KeyError, AttributeError):
                s["summary"] = "done"
        return Response(content=body, status_code=response.status_code, headers=dict(response.headers),
                        media_type=response.media_type)

    app.include_router(router)
    from services import recruiter  # T19: recruiter flow routes (additive), before the static mounts
    app.include_router(recruiter.router)
    app.mount("/demo", StaticFiles(directory=str(ROOT / "demo")), name="demo")  # public demo samples only
    app.mount("/ui", StaticFiles(directory=str(ROOT / "ui"), html=True), name="ui")


async def forward_to_n8n(files: dict, data: dict) -> httpx.Response:
    """The only place the webhook token is used: read from .env per call, sent as a header to n8n, never returned,
    logged or stored."""
    headers = {"X-HireSignal-Token": env("WEBHOOK_TOKEN", "")}
    async with httpx.AsyncClient(timeout=float(env("UI_RUN_TIMEOUT_S", "1800"))) as client:
        return await client.post(WEBHOOK, files=files, data=data, headers=headers)


@router.post("/ui/run")
async def ui_run(cv: UploadFile = File(...), job_text: str | None = Form(None), job_file: UploadFile | None = File(None),
                 requirements: UploadFile | None = File(None), requirements_text: str | None = Form(None)):
    if _lock.locked():
        raise HTTPException(409, "A run is already in progress")
    async with _lock:
        content = await cv.read()
        if not content:
            raise HTTPException(422, "The CV file is empty.")
        if len(content) > MAX_UPLOAD:
            raise HTTPException(413, "The CV file is larger than 10 MB.")
        job = job_text or ""
        if job_file is not None:
            job = (await job_file.read()).decode("utf-8", errors="replace")
        if not job.strip():
            raise HTTPException(422, "Paste the job text or choose a .txt file.")
        card = requirements_text or ""
        if requirements is not None:
            card = (await requirements.read()).decode("utf-8", errors="replace")
        total = None
        if card.strip():
            try:
                total = len(json.loads(card)["requirements"])
            except (ValueError, KeyError, TypeError) as exc:
                raise HTTPException(422, "The requirements card is not valid JSON with a 'requirements' list.") from exc
        _reset(total)
        data = {"job_text": job}
        if card.strip():
            data["requirements"] = card
        try:
            r = await forward_to_n8n({"cv": (cv.filename or "cv", content, cv.content_type or "application/octet-stream")},
                                     data)
        except httpx.HTTPError as exc:
            _state.update(active=False, finished=time.time(), error=f"n8n not reachable ({type(exc).__name__})")
            raise HTTPException(502, "n8n is not reachable at the webhook URL. Is n8n running?") from exc
        _state.update(active=False, finished=time.time())
        try:
            reply = r.json()
        except ValueError:
            _state["error"] = f"n8n answered HTTP {r.status_code} without JSON"
            raise HTTPException(502, f"n8n answered HTTP {r.status_code} without JSON")
        if r.status_code >= 400:
            _state["error"] = f"n8n answered HTTP {r.status_code}"
        _last.clear()
        _last.update(reply if isinstance(reply, dict) else {"reply": reply})
        return JSONResponse(reply, status_code=r.status_code)


@router.get("/ui/progress")
def ui_progress_get():
    return progress_snapshot()


@router.get("/ui/last-result")
def ui_last_result():
    if not _last:
        raise HTTPException(404, "No run yet")
    return _last


__all__ = ["install", "summarise", "progress_snapshot", "forward_to_n8n", "Path"]
