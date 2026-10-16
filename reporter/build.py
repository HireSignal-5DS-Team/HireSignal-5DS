"""Deterministic part of the Report Writer: Pipeline.run() output dict -> Report (no model, always works).

It copies fields from the pipeline output and phrases them with fixed templates. It adds no claim: every sentence
restates a decision, a basis, a count or a verbatim CV quote that is already in the input.
"""
from .schema import (BiasView, Evidence, JudgeView, KnowledgeShown, ModelView, Overview, Report, ReporterProvenance,
                     RequirementSection, TextSection)

RENDERER = "reporter.deterministic.v1"

BASIS_WORDS = {
    "supported": "the CV text supports it",
    "contradicted": "the CV text shows it is not met",
    "not_documented": "the CV does not mention it (absence of evidence, not proof of absence)",
    "ambiguous": "the CV evidence is unclear or partial",
}


def _model_view(p):
    p = p or {}
    a = p.get("adapter")
    return ModelView(answered_by=p.get("answered_by"), model_id=p.get("model_id"), served_alias=p.get("served_alias"),
                     adapter=f"{a.get('repo')}@{(a.get('sha') or '')[:8]}" if a else None, prompt_id=p.get("prompt_id"),
                     knowledge_provider=p.get("knowledge_provider"), mock=bool(p.get("MOCK")),
                     replayed_from=p.get("replayed_from"))


def _judge_view(j):
    if not j:
        return JudgeView(verdict="not run")
    return JudgeView(verdict=j.get("judge_verdict") or "not run", score=j.get("judge_score"), nli_probs=j.get("nli_probs"),
                     model=j.get("model"), disagrees=j.get("judge_disagrees"), error=j.get("error"))


def _bias_view(b):
    return BiasView(audit_status=b.get("audit_status", "NOT_TESTED"), counterfactual_flip=b.get("counterfactual_flip"),
                    affected_attribute=b.get("affected_attribute"), leakage_terms=list(b.get("leakage_terms") or []),
                    demographic_evidence=bool(b.get("demographic_evidence")),
                    requires_human_review=bool(b.get("requires_human_review")))


def requirement_note(row):
    """Deterministic one-sentence note (also the fallback when the SLM text is rejected)."""
    d, basis = row["final_decision"], row["basis"]
    q = row["evidence"][0] if row["evidence"] else None
    end = "" if q and q.rstrip()[-1:] in ".!?" else "."
    if d == "MET":
        s = f'MET: the CV states "{q}"{end}' if q else "MET: the CV text supports it."
    elif d == "MISSING" and basis == "contradicted" and q:
        s = f'MISSING: the CV states "{q}", which does not meet it.'
    elif d == "MISSING":
        s = f"MISSING: {BASIS_WORDS.get(basis, basis)}."
    else:
        s = f"UNCERTAIN: {BASIS_WORDS.get(basis, 'the evidence is unclear')}."
    return s + (" A human reviewer must check it." if row["requires_human_review"] else "")


def executive_summary(out):
    s = out["summary"]
    n = len(out["requirements"])
    return (f"{n} requirement(s) were checked against the CV: {s['MET']} MET, {s['MISSING']} MISSING and "
            f"{s['UNCERTAIN']} UNCERTAIN. {s['must_met']} of {s['must_total']} must-have requirement(s) are MET. "
            f"{s['requires_human_review']} requirement(s) need human review.")


def facts_for_requirement(row):
    """The verified facts the SLM may use for one requirement note (and the validator checks against)."""
    return {"requirement": row["requirement_text"], "kind": row["kind"] + "-have",
            "decision": row["final_decision"], "basis": row["basis"], "evidence_quotes": list(row["evidence"]),
            "needs_human_review": bool(row["requires_human_review"])}


def facts_for_summary(out):
    s = out["summary"]
    return {"requirements_checked": len(out["requirements"]), "MET": s["MET"], "MISSING": s["MISSING"],
            "UNCERTAIN": s["UNCERTAIN"], "must_have_met": s["must_met"], "must_have_total": s["must_total"],
            "nice_to_have_total": len(out["requirements"]) - s["must_total"], "need_human_review": s["requires_human_review"],
            "requirements": [{"requirement": r["requirement_text"], "kind": r["kind"] + "-have",
                              "decision": r["final_decision"]} for r in out["requirements"]]}


def _det(text):
    return TextSection(text=text, writer="deterministic")


def build_report(out, job_title=None, notes=None, summary=None, slm_info=None, slm_status="off"):
    """Report from a Pipeline.run() dict. `notes` ({req_id: TextSection}) and `summary` (TextSection) are given by the
    SLM layer (reporter.writer); without them every text is the deterministic template."""
    notes = notes or {}
    sections = []
    for r in out["requirements"]:
        refs = r.get("citations") or [{"source_id": s} for s in r.get("rag_refs", [])]
        sections.append(RequirementSection(
            req_id=r["req_id"], requirement_text=r["requirement_text"], kind=r["kind"], decision=r["final_decision"],
            model_decision=r.get("model_decision"), basis=r["basis"],
            evidence=[Evidence(quote=q, span=tuple(sp)) for q, sp in zip(r["evidence"], r["evidence_spans"])],
            knowledge_shown=[KnowledgeShown(**{k: c.get(k) for k in ("source_id", "source_type", "title", "url", "retrieval")})
                             for c in refs],
            validator_reasons=list(r["validator"]["reasons"]), bias_audit=_bias_view(r["bias_audit"]),
            judge=_judge_view(r.get("judge")), requires_human_review=bool(r["requires_human_review"]),
            review_reasons=list(r["review_reasons"]), model=_model_view(r.get("provenance")),
            explanation=_det(r["explanation"]), plain_note=notes.get(r["req_id"]) or _det(requirement_note(r))))
    s = out["summary"]
    summ = summary or _det(executive_summary(out))
    texts = [summ] + [x.plain_note for x in sections]
    any_mock = any(x.model.mock for x in sections) or any(t.writer == "slm_mock" for t in texts) or "mock" in str(out.get("backend", {}).get("backend", "")).lower()
    return Report(
        overview=Overview(cv_id=out["cv_id"], job_id=out["job_id"], job_title=job_title,
                          counts={k: s[k] for k in ("MET", "MISSING", "UNCERTAIN")}, must_met=s["must_met"],
                          must_total=s["must_total"], requires_human_review=s["requires_human_review"]),
        executive_summary=summ, requirements=sections,
        provenance=ReporterProvenance(
            renderer=RENDERER, slm=slm_info, slm_status=slm_status, sections_total=len(texts),
            sections_slm=sum(t.writer in ("slm", "slm_mock") for t in texts),
            sections_fallback=sum(t.writer == "deterministic_fallback" for t in texts),
            pipeline={"backend": {k: v for k, v in (out.get("backend") or {}).items() if k != "results"},
                      "knowledge": out.get("knowledge"), "judge": out.get("judge"), "parser": out.get("parser")},
            any_mock=any_mock))
