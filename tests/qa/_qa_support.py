"""Shared helpers for the S5 QA suite (MOCK backends only: no model weights, no LLM server).

`defect("QA-xxx")` marks a test that reproduces a defect logged in docs/qa/FAILURES.md. It is a strict xfail: when the
owning session fixes the defect the test XPASSes, the suite fails, and the marker must be removed (the regression
test then stays as a normal test).
"""
import json

import pytest

from matcher import CV, Job, Requirement
from matcher.schemas import KnowledgeRef
from matcher.validate import parse_model_output, validate

BACKEND_LABEL = "MOCK"  # every result produced with these helpers is a mock result, never a model result


def defect(qa_id, owner=None):
    who = f" (owner {owner})" if owner else ""
    return pytest.mark.xfail(strict=True, reason=f"{qa_id}{who}: open defect, see docs/qa/FAILURES.md")


def ans(decision, basis, evidence=(), expl="scripted"):
    return json.dumps({"decision": decision, "basis": basis, "evidence": list(evidence), "explanation": expl})


def check(decision, basis, evidence, cv, req, refs=(), expl="scripted"):
    """Validated RequirementResult for a scripted model answer."""
    return validate(parse_model_output(ans(decision, basis, evidence, expl)), cv, req, list(refs))


def req(req_id="r1", text="Hands-on Kubernetes experience", **kw):
    return Requirement(req_id=req_id, text=text, **kw)


def ref(source_id, title, aliases=(), text=None, source_type="esco", score=None, retrieval="fixture.qa"):
    return KnowledgeRef(source_type=source_type, source_id=source_id, title=title, aliases=list(aliases),
                        text=text or f"{title}. Also known as: {'; '.join(aliases) or title}. ", relevance_score=score,
                        retrieval=retrieval)


CV_TEXT = """Candidate profile (anonymised)

Experience
- Senior Python developer at a fintech scale-up (2019 - present).
- Set up Maven builds for twelve Java services.
- Never used Kubernetes in production; deployments ran on managed VMs.
- 6 years of JavaScript development.
- No experience with Kafka so far.
- Completed an online course on AWS Solutions Architect topics.

Education
- MSc in Computer Science (2018)."""
CVX = CV(cv_id="qa-cv-1", text=CV_TEXT)
JOB = Job(job_id="qa-job-1", title="Backend engineer", requirements=[
    {"req_id": "r1", "text": "At least 5 years of Python", "category": "experience", "skill_terms": ["Python"], "min_years": 5},
    {"req_id": "r2", "text": "Experience with Apache Maven", "skill_terms": ["Apache Maven"]},
    {"req_id": "r3", "text": "Hands-on Kubernetes experience", "skill_terms": ["Kubernetes"]},
    {"req_id": "r4", "text": "Experience with Apache Kafka", "skill_terms": ["Apache Kafka"], "kind": "nice"},
])
GOOD = {
    "r1": ("MET", "supported", ["Senior Python developer at a fintech scale-up (2019 - present)."]),
    "r2": ("MET", "supported", ["Set up Maven builds for twelve Java services."]),
    "r3": ("MISSING", "contradicted", ["Never used Kubernetes in production; deployments ran on managed VMs."]),
    "r4": ("MISSING", "not_documented", []),
}


REQUIRED_PROVENANCE = ("model_id", "base_revision", "adapter_id", "adapter_revision", "knowledge", "knowledge_version",
                       "prompt_version")


def provenance_problems(backend):
    """Missing provenance items for the primary model of a MatchReport.backend / Pipeline output dict."""
    primary = backend.get("primary", backend)
    flat = {**primary, **{k: v for k, v in backend.items() if k != "primary"}}
    out = [k for k in REQUIRED_PROVENANCE if k not in flat]
    for k in ("base_revision", "knowledge_version", "prompt_version"):
        if k in flat and not flat.get(k):
            out.append(f"{k} is empty")
    if flat.get("model_id", "").endswith("+lora") and not (flat.get("adapter_id") and flat.get("adapter_revision")):
        out.append("LoRA primary without adapter repo + sha")
    return out


class Scripted:
    """OpenAICompatBackend stand-in. mode: ok | down | raise. Records last_call like the real backend."""

    def __init__(self, model="mock-model", answers=None, fn=None, mode="ok"):
        self.model, self.answers, self.fn, self.mode, self.calls, self.tasks = model, answers or GOOD, fn, mode, 0, []
        self.last_call = {}

    def info(self):
        return {"backend": "mock", "label": BACKEND_LABEL, "model_id": self.model, "is_model": False}

    def generate(self, task):
        self.calls += 1
        self.tasks.append(task)
        if self.mode == "down":
            self.last_call = {"error": "URLError: connection refused", "latency_s": 0.0}
            return ""
        if self.mode == "raise":
            raise RuntimeError("backend exploded")
        self.last_call = {"error": None, "latency_s": 0.0}
        if self.fn:
            return self.fn(task)
        return ans(*self.answers[task.req.req_id])
