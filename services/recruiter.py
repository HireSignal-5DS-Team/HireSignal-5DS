"""T19: recruiter flow (one job card, up to 3 candidates, evidence comparison, human-approved letters).

A view and workflow layer on top of the unchanged pipeline (n8n workflow, prompts, models, gate, /report contract):
- POST /ui/card/validate      a recruiter card -> the webhook's `requirements` format (validated with RequirementIn)
- POST /ui/card/merge         merge selected requirements ("X or Y"), e.g. to undo the Job Agent's "or similar" split
- POST /ui/batch              1-3 CVs, the SAME confirmed card for each, run one after another through the webhook
- GET  /ui/batch/status       per-candidate status + the T16 live progress of the running one + the column order
- GET  /ui/batch/{id}/result/{label}   one candidate's result (stored under private/batches/<id>/)
- POST /ui/letter             the letter for the recruiter's decision (gate letter, recruiter-form letter, or the
                              existing human-decision /report path for an override); never sent anywhere
- POST /ui/approve            the recruiter approves: letter to eval/outbox/<decision>/, one audit line
- POST /ui/identity           after Approve only: name + e-mail from private/<cv_id>.json, to the page only

No ranking: columns are ordered by gate outcome (invite, review, reject) then upload order, never by score.
Identity values are never logged, sent to n8n or written outside private/; the audit log holds no CV text and no identity.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ValidationError

from services import ui
from services.config import ROOT, env
from services.contracts import RequirementIn

PRIVATE = ROOT / env("PRIVATE_DIR", "private")
OUTBOX = ROOT / "eval/outbox"
AUDIT = OUTBOX / "decision_log.jsonl"
MAX_CANDIDATES = 3
LABELS = ["A", "B", "C"]
OUTCOME_RANK = {"invite": 0, "review": 1, "reject": 2}
IMAGE_TYPES = {"image"}

router = APIRouter()
_batch: dict = {}


# ------------------------------------------------------------------ card ---

def validate_card(card: dict) -> tuple[dict | None, list[str]]:
    """A recruiter card -> (the webhook `requirements` JSON, errors). Same schema as demo/*_requirements_*.json."""
    errors: list[str] = []
    if not isinstance(card, dict) or not isinstance(card.get("requirements"), list) or not card["requirements"]:
        return None, ["The card needs a non-empty 'requirements' list."]
    out, seen = [], set()
    for i, r in enumerate(card["requirements"], start=1):
        where = f"row {i}"
        if not isinstance(r, dict):
            errors.append(f"{where}: not an object")
            continue
        req = {"req_id": str(r.get("req_id") or f"r{i}").strip(), "text": str(r.get("text") or "").strip(),
               "kind": r.get("kind") or "must", "category": r.get("category") or "skill",
               "skill_terms": [str(t).strip() for t in (r.get("skill_terms") or []) if str(t).strip()],
               "min_years": None if r.get("min_years") in (None, "") else r.get("min_years")}
        try:
            RequirementIn(**req)
        except ValidationError as exc:
            errors += [f"{where} ({req['req_id']}): {e['loc'][-1]}: {e['msg']}" for e in exc.errors()]
            continue
        if req["req_id"] in seen:
            errors.append(f"{where}: duplicate id {req['req_id']}")
            continue
        seen.add(req["req_id"])
        req["min_years"] = None if req["min_years"] is None else float(req["min_years"])
        out.append({**req, "evidence": str(r.get("evidence") or req["text"])})
    if errors:
        return None, errors
    return {"job_id": str(card.get("job_id") or "job-recruiter"), "title": str(card.get("title") or ""),
            "confirmed_by": "recruiter (UI)", "requirements": out}, []


def merge_requirements(reqs: list[dict], ids: list[str]) -> list[dict]:
    """Merge the selected rows into the first one: texts joined with " or ", union of skill terms (order kept).
    Kind, category and evidence come from the first selected row; min_years = the smallest stated."""
    chosen = [r for r in reqs if r.get("req_id") in set(ids)]
    if len(chosen) < 2:
        raise ValueError("Select at least two requirements to merge.")
    first = chosen[0]
    terms: list[str] = []
    for r in chosen:
        terms += [t for t in r.get("skill_terms") or [] if t not in terms]
    years = [float(r["min_years"]) for r in chosen if r.get("min_years") not in (None, "")]
    merged = {**first, "text": " or ".join(dict.fromkeys(str(r.get("text") or "").strip() for r in chosen)),
              "skill_terms": terms, "min_years": min(years) if years else None}
    out = []
    for r in reqs:
        if r is first:
            out.append(merged)
        elif r not in chosen:
            out.append(r)
    return out


@router.post("/ui/card/validate")
def card_validate(card: dict):
    clean, errors = validate_card(card)
    if errors:
        raise HTTPException(422, {"errors": errors})
    return clean


class MergeIn(BaseModel):
    requirements: list[dict]
    ids: list[str]


@router.post("/ui/card/merge")
def card_merge(body: MergeIn):
    try:
        return {"requirements": merge_requirements(body.requirements, body.ids)}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# ------------------------------------------------------------------ facts ---

def candidate_facts(result: dict) -> dict:
    """Counts only (no score): must-haves met / unclear, nice-to-haves met."""
    reqs = result.get("requirements") or []
    must = [r for r in reqs if r.get("kind") == "must"]
    nice = [r for r in reqs if r.get("kind") == "nice"]
    met = sum(r.get("decision") == "MET" for r in must)
    return {"must_total": len(must), "must_met": met, "must_unclear": sum(r.get("decision") == "UNCERTAIN" for r in must),
            "nice_total": len(nice), "nice_met": sum(r.get("decision") == "MET" for r in nice),
            "all_must_met": bool(must) and met == len(must)}


def column_order(candidates: list[dict]) -> list[str]:
    """invite -> review -> reject (-> not finished), then upload order. Never the score."""
    return [c["label"] for c in sorted(candidates, key=lambda c: (OUTCOME_RANK.get(c.get("outcome"), 3), c["index"]))]


# ------------------------------------------------------------------ batch ---

def _public(c: dict) -> dict:
    return {k: c.get(k) for k in ("label", "index", "status", "outcome", "decided_by", "facts", "error", "elapsed_s",
                                  "is_image", "review_form_url", "execution_id")}


def batch_status() -> dict:
    if not _batch:
        return {"batch_id": None, "state": "none", "candidates": [], "order": []}
    cands = _batch["candidates"]
    return {"batch_id": _batch["batch_id"], "state": _batch["state"], "started": _batch["started"],
            "total": len(cands), "done": sum(c["status"] in ("done", "error") for c in cands),
            "candidates": [_public(c) for c in cands], "order": column_order(cands),
            "card": _batch.get("card"),  # the confirmed card (job data only)
            "progress": ui.progress_snapshot() if _batch["state"] == "running" else None}


async def _run_batch(files: list[tuple[str, bytes, str]], card_json: str, job_text: str, total: int) -> None:
    folder = PRIVATE / "batches" / _batch["batch_id"]
    folder.mkdir(parents=True, exist_ok=True)
    try:
        for c, (name, content, ctype) in zip(_batch["candidates"], files):
            c["status"], t = "running", time.time()
            ui._reset(total)
            try:
                r = await ui.forward_to_n8n({"cv": (f"cv{_suffix(name)}", content, ctype)},
                                            {"job_text": job_text, "requirements": card_json})
                res = r.json()
                if r.status_code >= 400 or not isinstance(res, dict) or "outcome" not in res:
                    raise RuntimeError(f"n8n answered HTTP {r.status_code}")
                (folder / f"{c['label']}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), "utf-8")
                c.update(status="done", outcome=res.get("outcome"), decided_by=res.get("decided_by"),
                         facts=candidate_facts(res), cv_id=res.get("cv_id"), execution_id=res.get("execution_id"),
                         review_form_url=res.get("review_form_url"))
            except Exception as exc:  # noqa: BLE001 - one candidate failing must not stop the others
                c.update(status="error", error=f"{type(exc).__name__}: the run failed (see the n8n Executions)")
            finally:
                c["elapsed_s"] = round(time.time() - t, 1)
                ui._state.update(active=False, finished=time.time())
        _batch["state"] = "done"
    finally:
        (folder / "batch_summary.json").write_text(json.dumps(
            {"batch_id": _batch["batch_id"], "started": _batch["started"], "finished": time.time(),
             "card": json.loads(card_json), "candidates": [{**_public(c), "cv_id": c.get("cv_id")}
                                                          for c in _batch["candidates"]],
             "order": column_order(_batch["candidates"]),
             "note": "file names are not stored (they can contain names); labels are A/B/C in upload order"},
            indent=1, ensure_ascii=False), "utf-8")
        if _batch["state"] != "done":
            _batch["state"] = "error"
        ui._lock.release()


def _suffix(name: str) -> str:
    m = re.search(r"\.[A-Za-z0-9]{1,5}$", name or "")
    return m.group(0).lower() if m else ""


@router.post("/ui/batch", status_code=202)
async def start_batch(cvs: list[UploadFile] = File(...), card: str = Form(...), job_text: str = Form("")):
    if ui._lock.locked():
        raise HTTPException(409, "A run is already in progress")
    if not 1 <= len(cvs) <= MAX_CANDIDATES:
        raise HTTPException(422, f"Upload 1 to {MAX_CANDIDATES} CV files.")
    try:
        clean, errors = validate_card(json.loads(card))
    except ValueError:
        clean, errors = None, ["The card is not valid JSON."]
    if errors:
        raise HTTPException(422, "; ".join(errors))
    files = []
    for f in cvs:
        content = await f.read()
        if not content:
            raise HTTPException(422, "One of the CV files is empty.")
        if len(content) > ui.MAX_UPLOAD:
            raise HTTPException(413, "A CV file is larger than 10 MB.")
        files.append((f.filename or "cv", content, f.content_type or "application/octet-stream"))
    await ui._lock.acquire()  # released by _run_batch; /ui/run answers 409 meanwhile
    _batch.clear()
    _batch.update({"batch_id": datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4], "state": "running",
                   "started": time.time(), "card": clean,
                   "candidates": [{"label": LABELS[i], "index": i, "status": "waiting",
                                   "is_image": _suffix(n) in (".jpg", ".jpeg", ".png")}
                                  for i, (n, _, _) in enumerate(files)]})
    asyncio.get_running_loop().create_task(
        _run_batch(files, json.dumps(clean, ensure_ascii=False), job_text or clean["title"] or "job",
                   len(clean["requirements"])))
    return batch_status()


@router.get("/ui/batch/status")
def get_batch_status():
    return batch_status()


def _result(batch_id: str, label: str) -> dict:
    if not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{4}", batch_id) or label not in LABELS:
        raise HTTPException(404, "Unknown batch or candidate")
    path = PRIVATE / "batches" / batch_id / f"{label}.json"
    if not path.exists():
        raise HTTPException(404, "No result for this candidate yet")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/ui/batch/{batch_id}/result/{label}")
def get_result(batch_id: str, label: str):
    return _result(batch_id, label)


# ---------------------------------------------------------------- letters ---

class LetterIn(BaseModel):
    batch_id: str
    label: str
    decision: str


def _human_letter(res: dict, decision: str, card: dict | None) -> dict:
    """The existing human-decision path (T13): /report with decided_by='human', the body n8n's
    'Report Writer (human decision)' node builds. Called in process; the /report contract is unchanged."""
    from services import api
    from services.contracts import ReportIn
    terms = {q["req_id"]: q for q in (card or {}).get("requirements", [])}
    body = ReportIn(cv_id=res.get("cv_id"), job_title=res.get("job_title"), decided_by="human",
                    requirements=[{"req_id": q["req_id"], "kind": q["kind"], "text": q["text"],
                                   "decision": q["decision"], "quotes": [e["quote"] for e in q.get("quotes") or []],
                                   "judge": (q.get("judge") or {}).get("verdict"),
                                   "review_reasons": q.get("review_reasons") or [],
                                   "skill_terms": (terms.get(q["req_id"]) or {}).get("skill_terms") or [],
                                   "min_years": (terms.get(q["req_id"]) or {}).get("min_years"),
                                   "evidence_years": None} for q in res.get("requirements") or []],
                    outcome={"outcome": decision, "score": res.get("score"),
                             "rule": "decided by a recruiter in the recruiter flow",
                             "reasons": [*(res.get("reasons") or []), f"decided by a recruiter: {decision}"]},
                    reader={"mode": (res.get("reader") or {}).get("mode"),
                            "review_reasons": (res.get("reader") or {}).get("review_reasons") or []},
                    bias={"review_reasons": (res.get("bias") or {}).get("review_reasons") or [],
                          "swap": (res.get("bias") or {}).get("swap") or {}})
    out = api.report(body)
    return {"letter": out.report.get("candidate_letter") or "", "source": out.source,
            "how": "human-decision letter (Report Writer, checked)"}


def _form_letter(res: dict) -> dict | None:
    """After the recruiter form (review case), n8n writes eval/outbox/<decision>/<execution>_<cv_id>.json."""
    for d in ("invite", "reject"):
        p = OUTBOX / d / f"{res.get('execution_id')}_{res.get('cv_id')}.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("decided_by") == "human":
                return {"decision": d, "letter": data.get("letter") or "", "how": "letter written after the recruiter form"}
    return None


@router.post("/ui/letter")
def letter(body: LetterIn):
    if body.decision not in ("invite", "reject", "hold"):
        raise HTTPException(422, "decision must be invite, reject or hold")
    res = _result(body.batch_id, body.label)
    gate = res.get("outcome")
    if body.decision == "hold":
        return {"decision": "hold", "letter": "", "how": "hold: no letter is written"}
    if gate == "review":
        form = _form_letter(res)
        if form is None:
            return {"decision": body.decision, "letter": "", "needs_form": True, "review_form_url": res.get("review_form_url"),
                    "how": "review case: decide in the recruiter form first; its checked letter then appears here"}
        if form["decision"] != body.decision:
            return {"decision": body.decision, "letter": "", "how": f"the recruiter form already decided "
                    f"'{form['decision']}'; choose that decision or decide again in n8n"}
        return {"decision": body.decision, **form}
    if body.decision == gate:
        return {"decision": gate, "letter": (res.get("report") or {}).get("candidate_letter") or "",
                "source": (res.get("report") or {}).get("source"), "how": "the gate's decision: the Report Writer's letter"}
    summary = PRIVATE / "batches" / body.batch_id / "batch_summary.json"
    card = json.loads(summary.read_text(encoding="utf-8")).get("card") if summary.exists() else None
    return {"decision": body.decision, **_human_letter(res, body.decision, card),
            "override": f"the gate said {gate}; the recruiter decided {body.decision}"}


# ----------------------------------------------------------- approve, audit ---

class ApproveIn(LetterIn):
    letter: str = ""


def _audit(line: dict) -> None:
    OUTBOX.mkdir(parents=True, exist_ok=True)
    with AUDIT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def _approved(batch_id: str, label: str) -> dict | None:
    if not AUDIT.exists():
        return None
    last = None
    for line in AUDIT.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("batch_id") == batch_id and d.get("candidate") == label and d.get("event") == "approved":
            last = d
    return last


@router.post("/ui/approve")
def approve(body: ApproveIn):
    if body.decision not in ("invite", "reject", "hold"):
        raise HTTPException(422, "decision must be invite, reject or hold")
    res = _result(body.batch_id, body.label)
    letter_file = None
    if body.decision != "hold":
        if not body.letter.strip():
            raise HTTPException(422, "The letter is empty.")
        folder = OUTBOX / body.decision
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"recruiter_{body.batch_id}_{body.label}.json"
        path.write_text(json.dumps({"batch_id": body.batch_id, "candidate": body.label, "cv_id": res.get("cv_id"),
                                    "system_outcome": res.get("outcome"), "recruiter_decision": body.decision,
                                    "letter": body.letter, "approved_at": _now(),
                                    "note": "approved by a recruiter; not sent (the human sends it)"},
                                   indent=1, ensure_ascii=False), encoding="utf-8")
        letter_file = f"eval/outbox/{body.decision}/{path.name}"
    line = {"time": _now(), "event": "approved", "batch_id": body.batch_id, "candidate": body.label,
            "cv_id": res.get("cv_id"), "system_outcome": res.get("outcome"), "recruiter_decision": body.decision,
            "letter_file": letter_file, "identity_revealed": False}
    _audit(line)
    return line


class IdentityIn(BaseModel):
    batch_id: str
    label: str


@router.post("/ui/identity")
def identity(body: IdentityIn):
    """Name + first e-mail of an APPROVED candidate, for the recruiter's own mail app. Returned to the page only:
    nothing is logged (the access log holds only the path), and the audit line says only 'revealed: yes'."""
    ok = _approved(body.batch_id, body.label)
    if not ok or ok.get("recruiter_decision") == "hold":
        raise HTTPException(403, "Approve a decision with a letter first.")
    res = _result(body.batch_id, body.label)
    path = PRIVATE / f"{res.get('cv_id')}.json"
    ident = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    _audit({"time": _now(), "event": "identity_revealed", "batch_id": body.batch_id, "candidate": body.label,
            "cv_id": res.get("cv_id"), "system_outcome": res.get("outcome"),
            "recruiter_decision": ok.get("recruiter_decision"), "letter_file": ok.get("letter_file"),
            "identity_revealed": True})
    emails = ident.get("emails") or []
    return {"name": ident.get("name"), "email": emails[0] if emails else None,
            "found": bool(ident.get("name") or emails),
            "note": None if (ident.get("name") or emails) else "No name or e-mail was found in this CV (e.g. an "
                                                                "anonymised dataset CV)."}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
