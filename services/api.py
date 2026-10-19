"""Station API v1: one FastAPI app on port 8010, one endpoint per station, called by n8n (one node per station).

    POST /reader   CV file  -> random cv_id + metadata; raw text -> private/<cv_id>.reader.json (never returned)
    POST /profile  cv_id -> anonymised text + privacy counts + parsed profile; identity -> private/<cv_id>.json
    POST /job      job text -> requirements card + injection flags
    POST /match    anonymised CV text + ONE requirement -> checked decision with verified quotes (+ confidence check)
    POST /judge    anonymised CV text + requirement + /match result -> the result + NLI Judge finding (station 6)
    POST /outcome  all requirement results of a pair -> invite / review / reject + the rule that fired (station 8)
    GET  /health   the app is up;  GET /ready  also checks the LLM server

Run: .venv\\Scripts\\python -m uvicorn services.api:app --host 127.0.0.1 --port 8010  (scripts/start_stack.ps1)
"""
import json
import time
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from services.config import ROOT, env, llm_settings
from services.contracts import (BiasIn, BiasOut, Health, JobIn, JobOut, JudgeIn, JudgeOut, MatchIn, MatchOut,
                                OutcomeIn, OutcomeOut, ProfileIn, ProfileOut, RagSearchIn, RagSearchOut, ReaderOut,
                                ReportIn, ReportOut)
from services.bias.auditor import SWAP_FLIP, counterfactual, leakage_check, swap_decision
from services.outcome.gate import decide
from services.job import BackendError, JobAgentError, QwenChatClient, run_job_agent
from services.job.injection import injected_sentences
from services.matcher.matcher import match
from services.profile import new_cv_id, run_profile_agent
from services.reader import ReaderError, read_cv

# Adapted from team V2: integration/upstream.py (MAX_CV_BYTES, CV_EXTENSIONS) (feature/agent-integration @ a5a03ff)
MAX_CV_BYTES = 10 * 1024 * 1024
CV_EXTENSIONS = {".pdf", ".docx", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".txt", ".text", ".md"}
# a free-form job paragraph without headings is an expected fallback, not a review reason (V2 upstream.py)
BENIGN_JOB_WARNINGS = {"no requirement section found, the whole offer was used"}
PRIVATE = ROOT / env("PRIVATE_DIR", "private")

app = FastAPI(title="HireSignal station API", version="1")
MAX_JSON_BYTES = 2 * 1024 * 1024  # T13 (security): a JSON body larger than this is refused (413), never processed


@app.middleware("http")
async def limit_json_body(request, call_next):
    """Oversized JSON bodies -> 413 before parsing (CV uploads to /reader keep their own 10 MB limit)."""
    from fastapi.responses import JSONResponse
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            size = int(request.headers.get("content-length") or 0)
        except ValueError:
            size = 0
        if size > MAX_JSON_BYTES:
            return JSONResponse({"detail": f"JSON body larger than {MAX_JSON_BYTES // (1024 * 1024)} MB"}, status_code=413)
    return await call_next(request)


def matcher_guard(text: str) -> tuple[str, list[dict]]:
    """What stands between the anonymised CV and every model that reads it: the Bias Auditor leakage check (T11), then
    the removal of detected prompt-injection sentences (T14). Returns (text, flags); an injection flag carries the
    removed sentence (kept for the recruiter view, never sent to a model)."""
    from services.job.injection import sanitise_injection
    text, flags = leakage_check(text)
    text, removed = sanitise_injection(text)
    return text, flags + [{"kind": "injection", "rule": "injected sentence", "action": "sentence removed",
                           "sentence": x} for x in removed]


def _plain_llm(max_tokens):
    """The plain Qwen3-4B (LoRA scale 0) for Profile and Job, with V2's one retry on transient 5xx."""
    from services.job.qwen_retry import ResilientQwenChatClient
    return ResilientQwenChatClient(max_tokens=max_tokens, lora_scale=float(env("LLM_SCALE_PLAIN", "0")))


@app.get("/health", response_model=Health)
def health():
    return Health(status="ok")


@app.get("/ready", response_model=Health)
def ready():
    cfg = llm_settings()
    if cfg["backend"] == "cloud":
        return Health(status="ok", checks={"llm": "cloud backend (not probed)"})
    url = cfg["base_url"].rstrip("/").removesuffix("/v1") + "/health"
    try:
        ok = httpx.get(url, timeout=3).status_code == 200
    except httpx.HTTPError:
        ok = False
    if not ok:
        raise HTTPException(503, detail={"status": "not ready", "checks": {"llm": f"no answer from {url}"}})
    return Health(status="ok", checks={"llm": "ok"})


def _page_summary(d: dict) -> dict:
    """Reader page details without CV text: the low-trust lines themselves stay in private/<cv_id>.reader.json."""
    out = {k: v for k, v in d.items() if k != "low_trust_lines"}
    if "low_trust_lines" in d:
        out["low_trust_lines"] = len(d["low_trust_lines"])
    return out


@app.post("/reader", response_model=ReaderOut)
async def reader(file: UploadFile = File(...), mode: str | None = Form(None)):
    t = time.perf_counter()
    data = await file.read()
    ext = Path(file.filename or "").suffix.lower()
    if ext not in CV_EXTENSIONS:
        raise HTTPException(422, f"unsupported CV file type {ext or '(none)'}; supported: {', '.join(sorted(CV_EXTENSIONS))}")
    if len(data) > MAX_CV_BYTES:
        raise HTTPException(413, f"CV file is larger than {MAX_CV_BYTES // (1024 * 1024)} MB")
    try:
        # the real file name often holds the person's name: not used. mode: T10 (READER_MODE = the setup chosen on dev)
        r = read_cv(data, file_name=f"upload{ext}", mode=mode or env("READER_MODE", "late"))
    except ReaderError as exc:
        raise HTTPException(422, str(exc)) from exc
    cv_id = new_cv_id()
    PRIVATE.mkdir(exist_ok=True)
    (PRIVATE / f"{cv_id}.reader.json").write_text(json.dumps(r.to_dict(), ensure_ascii=False), encoding="utf-8")
    return ReaderOut(cv_id=cv_id, file_type=r.file_type, text_chars=len(r.text),
                     sections={k: len(v) for k, v in r.sections.items()},
                     read_path=r.page_routes, mode=r.mode, pages=[_page_summary(d) for d in r.page_details],
                     layout=r.layout, ocr_confidence=r.ocr_confidence,
                     needs_human_review=r.needs_human_review, warnings=r.warnings, review_reasons=r.review_reasons,
                     info_flags=[f"reader:{w}" for w in r.warnings],
                     elapsed_s=round(time.perf_counter() - t, 3))


@app.post("/profile", response_model=ProfileOut)
def profile(body: ProfileIn):
    t = time.perf_counter()
    src = PRIVATE / f"{body.cv_id}.reader.json"  # cv_id pattern-checked in ProfileIn: no path tricks
    if not src.exists():
        raise HTTPException(404, f"no Reader output for {body.cv_id}: call /reader first")
    read = json.loads(src.read_text(encoding="utf-8"))
    llm = _plain_llm(int(env("PROFILE_MAX_TOKENS", "768")))  # V2-only fix: bounded output (integration/upstream.py)
    try:
        res = run_profile_agent(read["text"], cv_id=body.cv_id, backend=llm, sections=read.get("sections"),
                                chunk_chars=int(env("PROFILE_CHUNK_CHARS", "800")), audit=matcher_guard)
    except BackendError as exc:
        raise HTTPException(503, f"LLM server error: {exc}") from exc
    PRIVATE.mkdir(exist_ok=True)
    (PRIVATE / f"{res.cv_id}.json").write_text(res.identity.model_dump_json(indent=1), encoding="utf-8")
    notes = res.profile.uncertain if res.profile else []
    review, info = [], []
    if res.report.leaks_left:
        review.append("profile:identity_leak_left")
    if not res.report.name_found:
        ident = res.identity
        # no name AND no contact data at all = an already-anonymised source (e.g. Djinni): shown, does not block
        no_contacts = not (ident.emails or ident.phones or ident.urls or ident.addresses)
        (info if no_contacts else review).append("profile:name_not_found")
    if any("answer cut off" in n or "unreadable answer" in n for n in notes):
        review.append("profile:partial_extraction_requires_review")
    removed = [f["sentence"] for f in res.bias_flags if f.get("kind") == "injection"]
    if removed:  # T14: the sentences were removed before parse / Matcher / Report Writer; a person still reviews
        review.append("profile:possible_prompt_injection")
        info.append("profile:injection_removed")
    info += sorted({f"bias:{f['kind']} {f['action']}" for f in res.bias_flags if f.get("kind") != "injection"})
    return ProfileOut(cv_id=res.cv_id, anonymised_text=res.text, privacy=res.report,
                      bias_flags=[f for f in res.bias_flags if f.get("kind") != "injection"],
                      injection_removed=removed, profile=res.profile,
                      review_reasons=review, info_flags=info, elapsed_s=round(time.perf_counter() - t, 3))


@app.post("/job", response_model=JobOut)
def job(body: JobIn):
    t = time.perf_counter()
    llm = _plain_llm(int(env("JOB_MAX_TOKENS", "768")))
    try:
        card = run_job_agent(body.job_text, body.job_id or f"job-{uuid.uuid4().hex[:8]}", llm)
    except JobAgentError as exc:
        raise HTTPException(422, str(exc)) from exc
    except BackendError as exc:
        raise HTTPException(503, f"LLM server error: {exc}") from exc
    # Untrusted job text: a requirement quoted from an instruction to the model is not a job requirement.
    injected = injected_sentences(body.job_text)
    dropped = [r.req_id for r in card.requirements if any(r.evidence and r.evidence in s for s in injected)]
    if dropped:
        keep = [r for r in card.requirements if r.req_id not in dropped]
        if not keep:
            raise HTTPException(422, "no requirement left after removing injected instructions")
        card = card.model_copy(update={"requirements": keep})
    review = []
    if card.needs_human_review or [w for w in card.warnings if w not in BENIGN_JOB_WARNINGS]:
        review.append("job_agent:validation_warnings")
    info = ["job_agent:no_requirement_section" for w in card.warnings if w in BENIGN_JOB_WARNINGS]
    if injected:
        review.append("job_agent:possible_prompt_injection")
    return JobOut(card=card, injection={"injected_sentences": injected, "dropped_req_ids": dropped},
                  review_reasons=review, info_flags=info, elapsed_s=round(time.perf_counter() - t, 3))


@app.post("/match", response_model=MatchOut, response_model_by_alias=True)
def match_one(body: MatchIn):
    t = time.perf_counter()
    try:
        refs = None if body.knowledge_refs is None else [r.model_dump() for r in body.knowledge_refs]
        out = match(body.cv_text, body.requirement.model_dump(), refs=refs, knowledge_name=body.knowledge)
    except httpx.HTTPError as exc:
        raise HTTPException(503, f"LLM server error: {type(exc).__name__}") from exc
    return MatchOut(**out, elapsed_s=round(time.perf_counter() - t, 3))


_JUDGE = None


def _judge():
    """The NLI Judge, loaded once (DeBERTa-v3-base-mnli-fever-anli, ~0.7 GB). Thresholds: chosen on dev in T07."""
    global _JUDGE
    if _JUDGE is None:
        import torch
        from services.judge.judge import NLIJudge
        device = env("JUDGE_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
        _JUDGE = NLIJudge(ROOT / env("JUDGE_MODEL_DIR", "models/DeBERTa-v3-base-mnli-fever-anli"),
                          tau_pass=float(env("JUDGE_TAU_PASS", "0.05")), tau_fail=float(env("JUDGE_TAU_FAIL", "0.15")),
                          device=device, template=env("JUDGE_HYPOTHESIS", "v2"))
    return _JUDGE


@app.post("/judge", response_model=JudgeOut, response_model_by_alias=True)
def judge(body: JudgeIn):
    t = time.perf_counter()
    m = body.match.model_dump(by_alias=True)
    finding = _judge().judge(body.cv_text, body.requirement.model_dump(), m)  # never sees knowledge refs as premise
    reasons = list(dict.fromkeys(m["review_reasons"] + finding["review_reasons"]))
    return JudgeOut(**(m | {"review_reasons": reasons, "needs_human_review": m["needs_human_review"] or bool(reasons),
                            "elapsed_s": round(m["elapsed_s"] + time.perf_counter() - t, 3), "judge": finding}))


@app.post("/outcome", response_model=OutcomeOut)
def outcome(body: OutcomeIn):
    """Plain-code gate (services/outcome/gate.py). Settings chosen on dev in T08b (eval/results/2026-10-18_outcome_gate):
    OUTCOME_T_INVITE 85, OUTCOME_PAIR_FLAGS info, OUTCOME_JUDGE all, OUTCOME_JUDGE_MET_MAX_CONF 0.999 (a Judge doubt on a
    MET must-have counts only when p(MET) < 0.999), OUTCOME_JUDGE_MAX_SUPPORT / OUTCOME_JUDGE_SKIP_PROVEN off."""
    try:
        res = decide([r.model_dump() for r in body.requirements], body.pair_review_reasons, body.pair_info_flags,
                     **_gate_settings())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return OutcomeOut(**res.to_dict(), cv_id=body.cv_id, job_id=body.job_id)


def _gate_settings() -> dict:
    def opt(name, default=""):  # empty = option off
        v = env(name, default)
        return float(v) if v else None

    return dict(t_invite=int(env("OUTCOME_T_INVITE", "85")), pair_flags=env("OUTCOME_PAIR_FLAGS", "info"),
                judge=env("OUTCOME_JUDGE", "all"), judge_met_max_conf=opt("OUTCOME_JUDGE_MET_MAX_CONF", "0.999"),
                judge_max_support=opt("OUTCOME_JUDGE_MAX_SUPPORT"),
                judge_skip_proven=env("OUTCOME_JUDGE_SKIP_PROVEN", "0") == "1")


@app.post("/bias", response_model=BiasOut)
def bias(body: BiasIn):
    """Station 5, Bias Auditor (services/bias/auditor.py, T11). Leakage flags of the Matcher input + the live swap test
    when the gate would decide automatically (invite / reject) and BIAS_SWAP=on (default): one counterfactual identity;
    an identical Matcher input means no LLM call; otherwise /match + /judge on the must-haves again; a changed
    must-have decision -> review reason bias:swap_flip (gate rule 0)."""
    from services.profile import anonymise_cv
    from services.reader.sections import split_sections
    t = time.perf_counter()
    src = PRIVATE / f"{body.cv_id}.reader.json"
    if not src.exists():
        raise HTTPException(404, f"no Reader output for {body.cv_id}: call /reader first")
    read = json.loads(src.read_text(encoding="utf-8"))
    ident = PRIVATE / f"{body.cv_id}.json"
    name = json.loads(ident.read_text(encoding="utf-8")).get("name") if ident.exists() else None
    original, flags = matcher_guard(anonymise_cv(read["text"], cv_id=body.cv_id, sections=read.get("sections")).text)
    flags = [f for f in flags if f.get("kind") != "injection"]
    results = [r.model_dump() for r in body.results]
    try:
        would_be = decide(results, body.pair_review_reasons, [], **_gate_settings()).outcome
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    swap: dict = {"ran": False}
    review = []
    if env("BIAS_SWAP", "on") != "on":
        swap["skipped"] = "BIAS_SWAP=off"
    elif would_be not in ("invite", "reject"):
        swap["skipped"] = f"gate would answer {would_be}: a person reviews it anyway"
    else:
        cf_text, info = counterfactual(read["text"], name)
        cf_input = matcher_guard(anonymise_cv(cf_text, cv_id=body.cv_id, sections=split_sections(cf_text)).text)[0]
        swap |= {"ran": True, **info, "identical_matcher_input": cf_input == original}
        must = {r["req_id"]: r["decision"] for r in results if r["kind"] == "must"}
        if cf_input != original:  # same input + temperature 0 = same decisions: only re-run when the input differs
            swapped = {}
            for req in (q.model_dump() for q in body.requirements if q.req_id in must):
                try:
                    m = match(cf_input, req, refs=_rag_refs(req, cf_input))
                except httpx.HTTPError as exc:
                    raise HTTPException(503, f"LLM server error: {type(exc).__name__}") from exc
                _judge().judge(cf_input, req, m)  # the Judge never changes a decision; run for parity with the chain
                swapped[req["req_id"]] = m["decision"]
            changed = swap_decision(must, swapped)
            swap |= {"must_rerun": len(swapped), "changed_must": changed}
            if changed:
                review.append(SWAP_FLIP)
        swap["latency_s"] = round(time.perf_counter() - t, 3)
    info_flags = sorted({f"bias:{f['kind']} {f['action']}" for f in flags})
    return BiasOut(cv_id=body.cv_id, bias_flags=flags, would_be_outcome=would_be, swap=swap, review_reasons=review,
                   info_flags=info_flags, elapsed_s=round(time.perf_counter() - t, 3))



@app.post("/report", response_model=ReportOut)
def report(body: ReportIn):
    """Station 7, Report Writer (services/report/, T12): Qwen3-4B plain (LoRA scale 0) writes the recruiter summary,
    the requirement lines, the candidate letter and the recruiter flags from the decision record only; the code fact
    checker reads it; one retry with the checker's errors; then the template (info flag report:template_fallback)."""
    from services.report.record import build_record
    from services.report.writer import write_report
    t = time.perf_counter()
    record = build_record([r.model_dump() for r in body.requirements], body.outcome, body.reader, body.bias,
                          body.job_title, decided_by=body.decided_by)
    try:
        out = write_report(record)
    except RuntimeError as exc:  # REPORT_FALLBACK is not "template"
        raise HTTPException(502, str(exc)) from exc
    return ReportOut(cv_id=body.cv_id, report=out["report"], source=out["source"], attempts=out["attempts"],
                     first_errors=out["first_errors"], retry_errors=out["retry_errors"], info_flags=out["info_flags"],
                     model=out["model"], elapsed_s=round(time.perf_counter() - t, 3))

def _rag_refs(req: dict, cv_text: str):
    """The knowledge refs /rag/search would give (V6: none when every skill term is already in the CV)."""
    from rag.retrieval import terms_in_cv
    if env("RAG_ONLY_WHEN_MISSING", "1") == "1" and terms_in_cv(req, cv_text):
        return []
    return _rag().lookup(req, k=3)


_RAG = None


def _rag():
    """The ESCO retriever chosen in T09 on dev (V6: dense all-MiniLM-L6-v2, chunking A, only when the terms are not
    in the CV; env RAG_*; see config/.env.example). Dense vectors live in Qdrant local mode
    (rag/index/, rebuilt at start: 1,621 vectors, a few seconds); BM25 needs no store."""
    global _RAG
    if _RAG is None:
        from rag.retrieval import EscoRetriever
        import torch
        _RAG = EscoRetriever(chunking=env("RAG_CHUNKING", "A"), search=env("RAG_SEARCH", "dense"),
                             embed=env("RAG_EMBED", "all-MiniLM-L6-v2") or None, reranker=env("RAG_RERANKER", "") or None,
                             graph=env("RAG_GRAPH", "0") == "1", store=env("RAG_STORE", "qdrant"),
                             device=env("RAG_DEVICE", "cuda" if torch.cuda.is_available() else "cpu"))
    return _RAG


@app.post("/rag/search", response_model=RagSearchOut)
def rag_search(body: RagSearchIn):
    """Station 4a: ESCO knowledge refs for one requirement (query = its skill terms or text, never CV text)."""
    from rag.retrieval import terms_in_cv
    t = time.perf_counter()
    req = body.requirement.model_dump()
    only_missing = env("RAG_ONLY_WHEN_MISSING", "1") == "1"
    skipped = bool(only_missing and body.cv_text and terms_in_cv(req, body.cv_text))
    r = _rag()
    refs = [] if skipped else r.lookup(req, k=body.k)
    return RagSearchOut(knowledge_refs=refs, retriever=r.name + (" +only-when-missing" if only_missing else ""),
                        skipped=skipped, elapsed_s=round(time.perf_counter() - t, 3))



# T16: demo page (a view only): progress middleware, /ui/run, /ui/progress, /ui/ static page. Installed last, so the
# station routes above keep priority and their contracts are unchanged.
from services.ui import install as _install_ui  # noqa: E402

_install_ui(app)
