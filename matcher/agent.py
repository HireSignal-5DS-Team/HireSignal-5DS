"""Matcher agent: CV + job requirements -> knowledge lookup -> SLM (or baseline) -> deterministic validation -> report.

Output path for one requirement: raw text -> parse_model_output (strict) -> if that fails, output_adapters.strict_repair
(form-only repairs, never a new or re-labelled decision) -> validate -> RequirementResult. The Matcher adds its own
review reasons (`MATCHER_REVIEW`) on top of the validator's, and records for every result which model answered
(provenance). Review routing never rejects: it only sends a result to a human.
"""
import time

from . import prompt
from .backends import Task
from .output_adapters import COSMETIC, strict_repair
from .schemas import MatchReport, MatchSummary
from .validate import parse_model_output, validate

# Matcher-level review reasons -> priority (rule signals, not probabilities). Documented in docs/MATCHER_INTEGRATION.md.
MATCHER_REVIEW = {
    "matcher:backend_unavailable": "high",    # every model endpoint failed; decision is the validator's UNCERTAIN
    "matcher:output_unparseable": "high",     # a model answered but no ModelAnswer could be read, even after repair
    "matcher:served_model_mismatch": "high",  # the endpoint does not list the alias we asked for (/v1/models)
    "matcher:fallback_model_used": "medium",  # the base model answered instead of the fine-tuned primary
    "matcher:output_repaired": "medium",      # the answer was readable only after a form repair (list in provenance)
}
_RANK = {"low": 0, "medium": 1, "high": 2}


def matcher_review(call, answer, repairs):
    reasons = []
    if call.get("error"):
        reasons.append("matcher:backend_unavailable")
    elif call.get("used") == "fallback":
        reasons.append("matcher:fallback_model_used")
    if answer is None and not call.get("error"):
        reasons.append("matcher:output_unparseable")
    if answer is not None and set(repairs) - COSMETIC:
        reasons.append("matcher:output_repaired")
    if (call.get("provenance") or {}).get("alias_verified") is False:
        reasons.append("matcher:served_model_mismatch")
    return reasons


def route(res, reasons):
    """RequirementResult with the Matcher's review reasons added. The decision is never touched."""
    if not reasons:
        return res
    prio = max([res.review_priority, *(MATCHER_REVIEW[r] for r in reasons)], key=_RANK.get)
    return res.model_copy(update={"review_reasons": list(dict.fromkeys(res.review_reasons + reasons)),
                                  "review_priority": prio, "needs_human_review": True})


def shown_label(ref):
    """The id label the p1 prompt shows for a knowledge entry (matcher/prompt.format_knowledge)."""
    return ref.source_id.rsplit("/", 1)[-1][:12]


class Matcher:
    def __init__(self, backend, knowledge, k=3, ref_year=2026):
        self.backend, self.knowledge, self.k, self.ref_year = backend, knowledge, k, ref_year

    def knowledge_info(self):
        return {"knowledge_provider": getattr(self.knowledge, "name", type(self.knowledge).__name__),
                "knowledge_version": getattr(self.knowledge, "version", None)}

    def result_provenance(self, call, repairs):
        """Who produced this one result. Mock/scripted backends are labelled MOCK, never presented as a model."""
        p = dict(call.get("provenance") or {})
        if not p:
            bi = self.backend.info() if hasattr(self.backend, "info") else {}
            p = {"model_id": call.get("model") or bi.get("model_id") or bi.get("label") or bi.get("backend"),
                 "adapter": None, "MOCK": not bi.get("is_model", False)}
        return {**p, "answered_by": None if call.get("error") else (call.get("used") or p.get("role") or "single"),
                **self.knowledge_info(), "prompt_id": prompt.PROMPT_VERSION, "repairs": repairs,
                "finish_reason": call.get("finish_reason"), "error": call.get("error"),
                "primary_error": call.get("primary_error")}

    def match_requirement(self, cv, req, job_id=None):
        use_job = job_id and getattr(self.knowledge, "uses_job", False)
        refs = self.knowledge.lookup(req, k=self.k, job_id=job_id) if use_job else self.knowledge.lookup(req, k=self.k)
        task = Task(cv, req, refs)  # the same refs are shown in the prompt and cited in rag_refs
        t0 = time.perf_counter()
        raw = self.backend.generate(task)
        latency = time.perf_counter() - t0
        call = dict(getattr(self.backend, "last_call", None) or {})
        answer, repairs = parse_model_output(raw), []
        if answer is None and raw:
            answer, repairs = strict_repair(raw)
        info = {"raw": raw, "latency_s": latency, "parsed": answer is not None, "repairs": repairs, "refs": refs,
                "call": call, "review": matcher_review(call, answer, repairs),
                "provenance": self.result_provenance(call, repairs)}
        return validate(answer, cv, req, refs, self.ref_year), info

    def report_backend(self, infos):
        """MatchReport.backend: the configured backend plus, per result, the provenance of the model that answered."""
        return {**self.backend.info(), "knowledge": self.knowledge_info()["knowledge_provider"], **self.knowledge_info(),
                "prompt_id": prompt.PROMPT_VERSION, "results": {rid: i["provenance"] for rid, i in infos}}

    def build_report(self, cv, job, pairs):
        results = [route(res, info["review"]) for res, info in pairs]
        musts = [r for r in results if r.kind == "must"]
        met = sum(r.decision == "MET" for r in musts)
        summary = MatchSummary(
            counts={d: sum(r.decision == d for r in results) for d in ("MET", "MISSING", "UNCERTAIN")},
            must_total=len(musts), must_met=met, must_coverage=round(met / len(musts), 3) if musts else None,
            needs_human_review=sum(r.needs_human_review for r in results))
        return MatchReport(cv_id=cv.cv_id, job_id=job.job_id, results=results, summary=summary,
                           backend=self.report_backend([(res.req_id, info) for res, info in pairs]))

    def match(self, cv, job):
        return self.build_report(cv, job, [self.match_requirement(cv, r) for r in job.requirements])
