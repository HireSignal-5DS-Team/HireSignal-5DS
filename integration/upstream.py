"""V2 document flow: CV file/text + job paragraph -> Reader -> Profile -> Job Agent -> the unchanged V1 pipeline.

    CV bytes/text --Reader--> clean text + sections --Profile (anonymise + parse)--> matcher CV (anonymised text)
    job paragraph --Job Agent--> JobRequirements card --to_matcher_job()--> matcher Job
    matcher CV + Job --V1 Pipeline.run (Matcher+RAG, validator, Bias, Judge)--> PipelineOutput (contract 1.1)

Evidence rule: the Matcher only ever sees `CV.text` = the Profile Agent's anonymised CV text, and every quote is
verified against it (spans index that text). The Profile Agent's parsed skills/experience go to
`CV.structured["profile"]`, which the Matcher and validator never use as evidence.
Identity values (name, e-mail, ...) never leave this function: only the privacy report is returned.
Every stage reports what really ran; a failed stage is never replaced by a fake success.
"""
import os
import re
import time
import uuid

from matcher.validate import _INJECT

# V1's injection pattern plus instructions addressed to the model ("assistant, ignore your rules").
_INJECT_EXTRA = re.compile(r"\b(ignore|disregard|forget)\s+(all\s+)?(your|the|these|previous|prior)\s+(rules|instructions|prompt)|"
                           r"\b(assistant|AI|model|system)\s*[,:]\s*(ignore|disregard|forget|add|mark|output)", re.I)


def injected_sentences(text):
    """Sentences (or lines) of untrusted text that address instructions to the model."""
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p for p in parts if _INJECT.search(p) or _INJECT_EXTRA.search(p)]

MAX_CV_BYTES = 10 * 1024 * 1024
CV_EXTENSIONS = {".pdf", ".docx", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".txt", ".text", ".md"}


class StageError(Exception):
    def __init__(self, stage, message, stages):
        super().__init__(f"{stage}: {message}")
        self.stage, self.message, self.stages = stage, message, stages


def upstream_llm(env=None):
    """The shared plain Qwen3-4B (no adapter) used by the Profile and Job agents."""
    from agents.job.backend import QwenChatClient
    env = os.environ if env is None else env
    return QwenChatClient(base_url=env.get("HS_UPSTREAM_LLM_URL") or env.get("HS_LLM_BASE_URL") or "http://127.0.0.1:8080/v1",
                          model=env.get("HS_UPSTREAM_LLM_MODEL") or "Qwen/Qwen3-4B-Instruct-2507",
                          max_tokens=int(env.get("HS_UPSTREAM_MAX_TOKENS", 3072)),
                          timeout=float(env.get("HS_UPSTREAM_TIMEOUT", 300)))  # CPU-only runs need ~1800


def _stage(stages, name, fn, progress=None, **meta):
    t0 = time.perf_counter()
    if progress is not None:
        progress({"stage": name, "status": "running"})
    try:
        out = fn()
    except Exception as e:  # noqa: BLE001  report, then stop: no fake success
        stages.append({"stage": name, "status": "failed", "error": f"{type(e).__name__}: {str(e)[:300]}",
                       "elapsed_s": round(time.perf_counter() - t0, 2), **meta})
        if progress is not None:
            progress(stages[-1])
        raise StageError(name, f"{type(e).__name__}: {e}", stages) from e
    stages.append({"stage": name, "status": "ok", "elapsed_s": round(time.perf_counter() - t0, 2), **meta})
    if progress is not None:
        progress(stages[-1])
    return out


def read_cv_input(cv_bytes=None, file_name=None, cv_text=None):
    """Validate and read the CV with the real Reader. Exactly one of cv_bytes / cv_text."""
    from agents.reader import read_cv
    if (cv_bytes is None) == (cv_text is None):
        raise ValueError("give exactly one of a CV file or CV text")
    if cv_text is not None:
        if not cv_text.strip():
            raise ValueError("CV text is empty")
        cv_bytes, file_name = cv_text.encode("utf-8"), "pasted.txt"
    if len(cv_bytes) > MAX_CV_BYTES:
        raise ValueError(f"CV file is larger than {MAX_CV_BYTES // (1024 * 1024)} MB")
    ext = os.path.splitext(file_name or "")[1].lower()
    if ext not in CV_EXTENSIONS:
        raise ValueError(f"unsupported CV file type {ext or '(none)'}; supported: {', '.join(sorted(CV_EXTENSIONS))}")
    return read_cv(cv_bytes, file_name=file_name).to_dict()


def analyze_documents(pipeline, job_text, cv_bytes=None, file_name=None, cv_text=None, job_id=None,
                      llm=None, detectors=(), progress=None):
    """Run the full V2 flow. Returns the V1 PipelineOutput plus `stages` and `upstream` (no identity values)."""
    from agents.job import run_job_agent
    from agents.profile import new_cv_id, run_profile_agent
    from integration.contract import validate_output

    stages = []
    llm = llm or upstream_llm()
    reader = _stage(stages, "reader", lambda: read_cv_input(cv_bytes, file_name, cv_text), progress=progress)
    stages[-1].update(file_type=reader.get("file_type"), pages=reader.get("pages"), ocr=reader.get("ocr_confidence") is not None,
                      needs_human_review=reader.get("needs_human_review"))
    cv_id = new_cv_id()
    prof = _stage(stages, "profile", lambda: run_profile_agent(reader["text"], cv_id=cv_id, backend=llm,
                                                              sections=reader.get("sections"), detectors=detectors), progress=progress)
    stages[-1].update(prompt_version=prof.profile.prompt_version if prof.profile else None,
                      leaks_left=prof.report.leaks_left, parsed=prof.profile is not None)
    cv = prof.to_matcher_cv(reader)
    card = _stage(stages, "job_agent", lambda: run_job_agent(job_text, job_id or f"job-{uuid.uuid4().hex[:8]}", llm), progress=progress)
    stages[-1].update(requirements=len(card.requirements), must=sum(r.kind == "must" for r in card.requirements),
                      needs_human_review=card.needs_human_review)
    job = card.to_matcher_job()
    # Untrusted job text: a requirement quoted from an instruction to the model is not a job requirement.
    job_inj = injected_sentences(job_text)
    dropped = [r for r in card.requirements if any(r.evidence and r.evidence in s for s in job_inj)]
    if dropped:
        ids = {r.req_id for r in dropped}
        job["requirements"] = [r for r in job["requirements"] if r["req_id"] not in ids]
        stages[-1].update(dropped_injected=len(dropped))
    if not job["requirements"]:
        stages[-1].update(status="failed", error="all requirements came from injected instructions")
        raise StageError("job_agent", "no requirement left after removing injected instructions", stages)
    out = _stage(stages, "matcher_pipeline", lambda: pipeline.run(cv, job), progress=progress)
    validate_output(out)
    review = []
    if reader.get("needs_human_review"):
        review.append("reader:low_confidence_or_ocr")
    if prof.report.leaks_left:
        review.append("profile:identity_leak_left")
    # A free-form job paragraph has no explicit section heading. Using the whole
    # paragraph is an expected fallback, not by itself a reason for human review.
    benign_job_warnings = {"no requirement section found, the whole offer was used"}
    material_job_warnings = [w for w in card.warnings if w not in benign_job_warnings]
    if card.needs_human_review or material_job_warnings:
        review.append("job_agent:validation_warnings")
    if job_inj:
        review.append("job_agent:possible_prompt_injection")
    if injected_sentences(reader["text"]):
        review.append("profile:possible_prompt_injection")  # parsed skills may come from the injected text
    out["stages"] = stages
    out["upstream"] = {"reader": cv["structured"].get("reader", {}),  # identity-scrubbed by the Profile Agent
                       "privacy": prof.report.model_dump(), "profile": prof.profile.model_dump() if prof.profile else None,
                       "job_card": card.model_dump(), "job_title": card.title, "review_reasons": review,
                       "dropped_injected_requirements": [r.model_dump() for r in dropped]}
    return out
