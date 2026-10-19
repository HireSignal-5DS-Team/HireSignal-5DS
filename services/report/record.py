"""The anonymised decision record of one CV x job pair (station 7 input, T12): what /outcome and /bias used, nothing
more. No identity, no CV text except the verified quotes."""
from __future__ import annotations

LOW_CONF = "match:low_confidence"


def build_record(requirements: list[dict], outcome: dict, reader: dict | None = None, bias: dict | None = None,
                 job_title: str | None = None, decided_by: str = "gate") -> dict:
    """requirements: [{req_id, kind, text, decision, quotes [str], judge (verdict), review_reasons, skill_terms,
    min_years, evidence_years}]; outcome: the gate result {outcome, score, rule, reasons}; reader: {mode,
    review_reasons}; bias: {review_reasons, swap {ran, changed_must}}."""
    reqs = [{"req_id": r["req_id"], "kind": r["kind"], "text": r["text"], "decision": r["decision"],
             "quotes": [q for q in r.get("quotes") or [] if q], "judge": r.get("judge"),
             "low_confidence": LOW_CONF in (r.get("review_reasons") or []),
             "review_reasons": list(r.get("review_reasons") or []), "skill_terms": list(r.get("skill_terms") or []),
             "min_years": r.get("min_years"), "evidence_years": r.get("evidence_years")} for r in requirements]
    reader = reader or {}
    bias = bias or {}
    return {"job_title": job_title, "decided_by": decided_by, "outcome": outcome["outcome"], "score": outcome["score"],
            "gate_rule": outcome.get("rule"), "gate_reasons": list(outcome.get("reasons") or []),
            "requirements": reqs,
            "reader": {"mode": reader.get("mode", "text"),
                       "review_reasons": [x for x in reader.get("review_reasons") or [] if x.startswith("reader:")]},
            "bias": {"review_reasons": list(bias.get("review_reasons") or []),
                     "swap_ran": bool((bias.get("swap") or {}).get("ran")),
                     "swap_changed_must": list((bias.get("swap") or {}).get("changed_must") or [])}}


def llm_view(record: dict) -> dict:
    """What the writer model sees: the record without internal codes it does not need."""
    return {"job_title": record["job_title"], "decided_by": record.get("decided_by", "gate"),
            "outcome": record["outcome"], "score": record["score"],
            "gate_reasons": record["gate_reasons"],
            "requirements": [{k: r[k] for k in ("req_id", "kind", "text", "decision", "quotes", "low_confidence",
                                                "min_years", "evidence_years")} | {"judge": r["judge"]}
                             for r in record["requirements"]],
            "flags": sorted(_flag_texts(record))}


def _flag_texts(record: dict) -> set[str]:
    out = set()
    rr = record["reader"]["review_reasons"]
    if rr:
        out.add("image quality: the CV image was hard to read (" + ", ".join(x.split(":", 1)[1] for x in rr) + ")")
    if "bias:swap_flip" in record["bias"]["review_reasons"]:
        out.add("identity swap: a must-have decision changed when only the candidate's identity was swapped ("
                + ", ".join(record["bias"]["swap_changed_must"]) + ")")
    low = [r["req_id"] for r in record["requirements"] if r["low_confidence"]]
    if low:
        out.add("low confidence: the Matcher was unsure on " + ", ".join(low))
    return out
