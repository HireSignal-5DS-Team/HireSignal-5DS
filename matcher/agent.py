"""Matcher agent: CV + job requirements -> knowledge lookup -> SLM (or baseline) -> deterministic validation -> report."""
import time

from .backends import Task
from .schemas import MatchReport, MatchSummary
from .validate import parse_model_output, validate


class Matcher:
    def __init__(self, backend, knowledge, k=3, ref_year=2026):
        self.backend, self.knowledge, self.k, self.ref_year = backend, knowledge, k, ref_year

    def match_requirement(self, cv, req, job_id=None):
        use_job = job_id and getattr(self.knowledge, "uses_job", False)
        refs = self.knowledge.lookup(req, k=self.k, job_id=job_id) if use_job else self.knowledge.lookup(req, k=self.k)
        t0 = time.perf_counter()
        raw = self.backend.generate(Task(cv, req, refs))
        latency = time.perf_counter() - t0
        answer = parse_model_output(raw)
        info = {"raw": raw, "latency_s": latency, "parsed": answer is not None, "refs": refs,
                "call": dict(getattr(self.backend, "last_call", None) or {})}
        return validate(answer, cv, req, refs, self.ref_year), info

    def match(self, cv, job):
        results = [self.match_requirement(cv, r)[0] for r in job.requirements]
        musts = [r for r in results if r.kind == "must"]
        met = sum(r.decision == "MET" for r in musts)
        summary = MatchSummary(
            counts={d: sum(r.decision == d for r in results) for d in ("MET", "MISSING", "UNCERTAIN")},
            must_total=len(musts), must_met=met, must_coverage=round(met / len(musts), 3) if musts else None,
            needs_human_review=sum(r.needs_human_review for r in results))
        return MatchReport(cv_id=cv.cv_id, job_id=job.job_id, results=results, summary=summary,
                           backend={**self.backend.info(), "knowledge": self.knowledge.name})
