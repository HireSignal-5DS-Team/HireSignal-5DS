"""Approved order: Parser -> RAG -> Matcher -> Python Validator -> Bias Auditor -> NLI Judge -> Aggregator
-> (human review) -> Report Writer.

Each stage only ADDS a finding; the validated Matcher decision is never replaced (`final_decision` is the validated
decision and `model_decision` the raw one). The Bias Auditor and the Judge both inspect the same validated
Matcher result: the Judge does not see the auditor's output and the auditor does not alter evidence.

Parser: teammates' Parser Agent is not in the repository. `StructuredInputParser` accepts already-structured
CV/Job JSON (the contract in LOCAL_INTEGRATION_HANDOFF.md); a real parser must return the same (CV, Job).
Report Writer: deterministic renderer (no LLM, so no new claims); a teammate's LLM Report Writer can consume
the same aggregated JSON.
"""
from .agent import Matcher, shown_label
from .bias_audit import check_result, counterfactual, merge
from .schemas import CV, Job


class StructuredInputParser:
    """Interface stand-in for the Parser Agent: input already follows matcher.schemas (CV, Job)."""
    name = "structured-input (Parser Agent not integrated)"

    def parse(self, cv_obj, job_obj):
        return CV.model_validate(cv_obj), Job.model_validate(job_obj)


def aggregate(res, bias, judge):
    """Transparent combination for one requirement. Review reasons are the union of every stage's reasons."""
    reasons = [f"validator:{r}" for r in res.review_reasons]
    if bias.requires_human_review:
        reasons.append(f"bias:{bias.affected_attribute or ('leakage' if bias.leakage_terms else 'demographic_evidence')}")
    if judge is not None:
        if judge.judge_verdict == "FAIL":
            reasons.append("judge:disagrees")
        elif judge.judge_verdict == "UNCERTAIN":
            reasons.append("judge:uncertain")
    if res.decision == "UNCERTAIN":
        reasons.append("decision:uncertain")
    reasons = list(dict.fromkeys(reasons))
    return {
        "req_id": res.req_id, "requirement_text": res.requirement_text, "kind": res.kind,
        "final_decision": res.decision, "model_decision": res.model_decision, "basis": res.basis,
        "evidence": res.evidence, "evidence_spans": res.evidence_spans, "explanation": res.explanation,
        "rag_refs": res.rag_refs,
        "validator": {"review_priority": res.review_priority, "reasons": res.review_reasons},
        "bias_audit": bias.to_dict(), "judge": judge.to_dict() if judge else None,
        "requires_human_review": bool(reasons),  # every reason above is review-worthy by design
        "review_reasons": reasons,
    }


class Pipeline:
    def __init__(self, backend, knowledge, judge=None, parser=None, counterfactual=None, k=3, live_counterfactual=False):
        """live_counterfactual: run the Bias Auditor's counterfactual test inline (8 extra Matcher calls per
        requirement). Default off: counterfactual audits normally run in batch (benchmark/bias_eval.py)."""
        self.matcher = Matcher(backend, knowledge, k=k)
        self.live_counterfactual = live_counterfactual
        self.judge, self.parser = judge, parser or StructuredInputParser()
        self.counterfactual = counterfactual or {}  # {req_id: BiasFinding} from a batch audit, optional

    def run(self, cv_obj, job_obj):
        cv, job = self.parser.parse(cv_obj, job_obj)
        pairs = [self.matcher.match_requirement(cv, r, job_id=job.job_id) for r in job.requirements]  # Matcher + Validator
        results = [res for res, _ in pairs]
        cf = dict(self.counterfactual)
        cf_models = {}  # req_id -> set of models that answered the counterfactual variants
        if self.live_counterfactual:  # Bias Auditor tests the deployed Matcher itself (it is the system under audit)
            for res, r in zip(results, job.requirements):
                seen = cf_models.setdefault(res.req_id, set())

                def fn(c, q, seen=seen):
                    out, info = self.matcher.match_requirement(c, q, job_id=job.job_id)
                    seen.add(info["provenance"].get("answered_by"))
                    return out
                cf[res.req_id] = counterfactual(fn, cv, r)
        audits = [merge(check_result(res, cv.text), cf.get(res.req_id)) for res in results]  # Bias
        judged = self.judge.judge_many([(res, cv, r) for res, r in zip(results, job.requirements)]) if self.judge \
            else [None] * len(results)  # Judge (after the auditor, on the same validated results)
        rows = [aggregate(res, b, j) for res, b, j in zip(results, audits, judged)]
        for row, (_, info) in zip(rows, pairs):
            row["citations"] = [{"source_id": x.source_id, "source_type": x.source_type, "title": x.title, "url": x.url,
                                 "retrieval": x.retrieval, "shown_as": shown_label(x)} for x in info["refs"]]
            call = info["call"]
            row["matcher_call"] = {k: call.get(k) for k in ("used", "model", "latency_s", "error", "primary_error",
                                                            "finish_reason") if k in call}
            row["provenance"] = info["provenance"]  # the model that answered THIS requirement
            if cf_models.get(row["req_id"], set()) - {info["provenance"].get("answered_by")}:
                # a counterfactual variant was answered by another model (or none): a flip may be a model switch
                info["review"] = info["review"] + ["matcher:counterfactual_mixed_models"]
            if info["review"]:  # fallback answer, backend down, unparseable/repaired output, wrong served model
                row["review_reasons"] = list(dict.fromkeys(row["review_reasons"] + info["review"]))
                row["requires_human_review"] = True
        musts = [r for r in rows if r["kind"] == "must"]
        report = self.matcher.build_report(cv, job, pairs)  # frozen MatchReport contract (validated by pydantic)
        return {"cv_id": cv.cv_id, "job_id": job.job_id, "parser": self.parser.name,
                "backend": report.backend, "knowledge": self.matcher.knowledge.name,
                "match_report": report.model_dump(mode="json"),
                "judge": getattr(self.judge, "name", None), "requirements": rows,
                "summary": {"MET": sum(r["final_decision"] == "MET" for r in rows),
                            "MISSING": sum(r["final_decision"] == "MISSING" for r in rows),
                            "UNCERTAIN": sum(r["final_decision"] == "UNCERTAIN" for r in rows),
                            "must_met": sum(r["final_decision"] == "MET" for r in musts), "must_total": len(musts),
                            "requires_human_review": sum(r["requires_human_review"] for r in rows),
                            "note": "Requirement-level screening aid. No automatic rejection or hiring decision."}}


def _who(p):
    if not p or p.get("answered_by") is None:
        return "no model (all Matcher endpoints failed)"
    a = p.get("adapter")
    return (f"{p['answered_by']} · {p.get('served_alias') or p.get('model_id')}"
            + (f" · adapter {a['repo']}@{a['sha'][:8]}" if a else " · no adapter") + (" · MOCK" if p.get("MOCK") else ""))


def write_report(out):
    """Report Writer (deterministic): markdown from the aggregated pipeline output. Adds no claims of its own."""
    s = out["summary"]
    lines = [f"# Matching report — CV `{out['cv_id']}` vs job `{out['job_id']}`", "",
             f"MET {s['MET']} · MISSING {s['MISSING']} · UNCERTAIN {s['UNCERTAIN']} · must-have met "
             f"{s['must_met']}/{s['must_total']} · **{s['requires_human_review']} requirement(s) need human review**", "",
             f"_{s['note']}_", "",
             f"Prompt `{out['backend'].get('prompt_id')}` · knowledge `{out['backend'].get('knowledge_provider')}`"
             + (" · **MOCK backend: not a model result**" if any((r.get("provenance") or {}).get("MOCK")
                                                                for r in out["requirements"]) else ""), ""]
    for r in out["requirements"]:
        j = r["judge"] or {}
        lines += [f"## {r['req_id']} ({r['kind']}-have): {r['requirement_text']}",
                  f"- Decision: **{r['final_decision']}** ({r['basis']}); model said {r['model_decision']}",
                  *(f"- Evidence: \"{q}\" (chars {a}-{b})" for q, (a, b) in zip(r["evidence"], r["evidence_spans"])),
                  f"- Explanation (model): {r['explanation']}",
                  f"- Validator: {', '.join(r['validator']['reasons']) or 'no issue'}",
                  f"- Bias audit: {r['bias_audit']['audit_status']}"
                  + (f" (flip on {r['bias_audit']['affected_attribute']})" if r["bias_audit"].get("counterfactual_flip") else ""),
                  f"- NLI judge: {j.get('judge_verdict', 'not run')}" + (f" (score {j['judge_score']})" if j.get("judge_score") is not None else ""),
                  f"- Answered by: {_who(r.get('provenance') or {})}",
                  f"- Human review: {'**REQUIRED** — ' + ', '.join(r['review_reasons']) if r['requires_human_review'] else 'not required'}",
                  ""]
    return "\n".join(lines)
