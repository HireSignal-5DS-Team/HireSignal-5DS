# Adapted from team V2: matcher/validate.py (find_span, evidence_years, validate) (feature/agent-integration @ a5a03ff)
"""Matcher validator v1: rules of evidence only (no rule tuned on bench-v1 val).

V2's validator v2 overfitted val (test macro-F1 0.678 after validation vs 0.887 raw, V2
benchmark/results/final/lora__gated/metrics.md). Here the code only checks what a quote proves:
  1. every quote must be an exact substring of the CV text (span verified); others are dropped.
     MET without a verified quote -> UNCERTAIN (+ review reason). No quote, no MET (CLAUDE.md rule 3).
  2. years: when the requirement has min_years, code reads the years written in the verified quotes and
     compares them with min_years ("the LLM judges, code counts", rule 2).
Plus two form rules of the output contract: an inconsistent decision/basis pair, and "contradicted" without a quote.
Each rule adds a review reason (review_reasons); the decision is only changed by the rules that say so below.
info_flags (shown, never block) is empty for now: every evidence rule above is a reason for human review.
"""
import re
from datetime import date

CONSISTENT = {"MET": {"supported"}, "MISSING": {"contradicted", "not_documented"}, "UNCERTAIN": {"ambiguous"}}


def find_span(cv_text, quote):
    """[start, end) of an exact occurrence, or None. Only surrounding whitespace is stripped."""
    q = quote.strip()
    i = cv_text.find(q) if q else -1
    return (i, i + len(q)) if i >= 0 else None


_YEARS = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", re.I)
_NUMWORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                         "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
_NUMWORD_YEARS = re.compile(rf"\b({'|'.join(_NUMWORDS)})(?=\s*\+?\s*(?:years?|yrs?)\b)", re.I)
_SINCE = re.compile(r"\bsince\s+((?:19|20)\d\d)\b", re.I)
_RANGE = re.compile(r"\b((?:19|20)\d\d)\s*(?:-|–|—|to)\s*((?:19|20)\d\d|present|now|current|today)\b", re.I)


def _norm_duration(q):
    """'Seven years' -> '7 years'; 'since 2018' -> '2018 - present' (V2 QA-032 duration forms)."""
    q = _NUMWORD_YEARS.sub(lambda m: str(_NUMWORDS[m.group(1).lower()]), q)
    return _SINCE.sub(lambda m: f"{m.group(1)} - present", q)


def evidence_years(quotes, ref_year=None):
    """Largest of: explicit 'N years' mentions, merged length of year ranges ('2019 - present'). None if none."""
    ref_year = ref_year or date.today().year
    quotes = [_norm_duration(q) for q in quotes]
    explicit = [float(m) for q in quotes for m in _YEARS.findall(q)]
    ranges = sorted((int(a), ref_year if not b.isdigit() else int(b)) for q in quotes for a, b in _RANGE.findall(q))
    merged = []
    for a, b in ranges:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    vals = explicit + ([sum(b - a for a, b in merged)] if merged else [])
    return max(vals) if vals else None


def validate(answer, cv_text, req, ref_year=None):
    """answer: the parsed model reply (dict with decision/basis/evidence/explanation) or None if invalid.
    req: dict with at least kind and optional min_years. Returns the checked result (dict)."""
    reasons = []
    if answer is None:
        decision, basis, raw_quotes, expl = "UNCERTAIN", "ambiguous", [], "Model output was not valid JSON for the schema."
        reasons.append("model_output_invalid")
    else:
        decision, basis, raw_quotes, expl = answer["decision"], answer["basis"], answer["evidence"], answer["explanation"]
        if basis not in CONSISTENT[decision]:
            decision, basis = "UNCERTAIN", "ambiguous"
            reasons.append("inconsistent_decision_basis")

    evidence = []
    for q in raw_quotes:
        span = find_span(cv_text, q)
        if span is None:
            reasons.append("evidence_not_in_cv")
        elif sum(ch.isalnum() for ch in cv_text[span[0]:span[1]]) < 3:
            reasons.append("evidence_too_short")
        elif all(e["start"] != span[0] or e["end"] != span[1] for e in evidence):
            evidence.append({"quote": cv_text[span[0]:span[1]], "start": span[0], "end": span[1]})
    quotes = [e["quote"] for e in evidence]

    if decision == "MET" and not quotes:  # rule 1: no verified quote, no MET
        decision, basis = "UNCERTAIN", "ambiguous"
        reasons.append("met_without_verified_evidence")
    if decision == "MISSING" and basis == "contradicted" and not quotes:
        basis = "not_documented"
        reasons.append("contradiction_without_evidence")

    years = None
    if req.get("min_years") and quotes:  # rule 2: code compares the years written in the evidence
        years = evidence_years(quotes, ref_year)
        if decision == "MET":
            if years is None:
                reasons.append("duration_not_in_evidence")  # flag only: V2 downgraded here and overfitted (QA-026/031)
            elif years < req["min_years"]:
                decision, basis = "UNCERTAIN", "ambiguous"
                reasons.append("years_below_minimum_in_evidence")
        elif decision == "MISSING" and basis == "contradicted" and years is not None and years >= req["min_years"]:
            reasons.append("contradiction_refuted_by_evidence")  # flag only

    reasons = list(dict.fromkeys(reasons))
    return {"decision": decision, "basis": basis, "evidence": evidence, "explanation": expl,
            "model_decision": answer["decision"] if answer else None, "evidence_years": years,
            "review_reasons": reasons, "info_flags": [], "needs_human_review": bool(reasons)}
