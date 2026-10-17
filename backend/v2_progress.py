"""In-memory, metadata-only progress for V2 synchronous analyses.

Never stores CVs, job text, raw model prompts or response bodies.
The progress token is unguessable and expires after 15 minutes of inactivity.
"""
from __future__ import annotations

import threading
import time
from uuid import UUID

_LOCK = threading.RLock()
_JOBS: dict[str, dict] = {}
TTL_S = 15 * 60
MAX_JOBS = 64


def valid_token(token: str) -> bool:
    if not isinstance(token, str) or len(token) != 36:
        return False
    try:
        return str(UUID(token, version=4)) == token.lower()
    except (ValueError, TypeError, AttributeError):
        return False


def _prune(now: float) -> None:
    for token, job in list(_JOBS.items()):
        # A model stage may legitimately run for many minutes; never expire it mid-inference.
        if job["status"] in ("running", "queued"):
            continue
        if now - job["updated"] > TTL_S:
            del _JOBS[token]
    if len(_JOBS) >= MAX_JOBS:
        for token, _ in sorted(_JOBS.items(), key=lambda pair: pair[1]["updated"])[:len(_JOBS) - MAX_JOBS + 1]:
            del _JOBS[token]


def start(token: str) -> None:
    if not valid_token(token):
        raise ValueError("invalid V2 progress token")
    now = time.monotonic()
    with _LOCK:
        _prune(now)
        _JOBS[token] = {"status": "queued", "stages": [], "created": now, "updated": now}


def set_status(token: str | None, status: str) -> None:
    if token is None:
        return
    with _LOCK:
        if job := _JOBS.get(token):
            job["status"] = status
            job["updated"] = time.monotonic()


def update(token: str | None, event: dict) -> None:
    if token is None:
        return
    # Only safe process metadata is retained. Never echo raw error text or CV quotes.
    stage = str(event.get("stage") or "")
    status = str(event.get("status") or "")
    if not stage or status not in ("running", "ok", "failed"):
        return
    now = time.monotonic()
    with _LOCK:
        if not (job := _JOBS.get(token)):
            return
        records: list[dict] = job["stages"]
        existing = next((record for record in records if record["stage"] == stage), None)
        if existing is None:
            existing = {"stage": stage, "status": "running", "_start": now}
            records.append(existing)
        existing["status"] = status
        if status == "running":
            existing["_start"] = now
        elif "elapsed_s" in event and isinstance(event["elapsed_s"], (int, float)):
            existing["elapsed_s"] = max(0.0, float(event["elapsed_s"]))
        job["updated"] = now


def snapshot(token: str) -> dict | None:
    now = time.monotonic()
    with _LOCK:
        _prune(now)
        job = _JOBS.get(token)
        if job is None:
            return None
        stages = []
        for record in job["stages"]:
            stage = {"stage": record["stage"], "status": record["status"]}
            if record["status"] == "running":
                stage["elapsed_s"] = round(now - record["_start"], 1)
            else:
                stage["elapsed_s"] = record.get("elapsed_s")
            stages.append(stage)
        return {"status": job["status"], "stages": stages,
                "elapsed_s": round(now - job["created"], 1)}
