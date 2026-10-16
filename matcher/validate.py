"""Deterministic post-processing of SLM output: JSON parsing, schema validation, verbatim-quote verification,
duration checks and review flags. The model proposes; these rules decide what is defensible."""
import json
import re

from pydantic import ValidationError

from .schemas import ModelAnswer, RequirementResult

CONSISTENT = {"MET": {"supported"}, "MISSING": {"contradicted", "not_documented"}, "UNCERTAIN": {"ambiguous"}}
HIGH, MEDIUM = "high", "medium"
# reason -> priority. Documented in docs/MATCHER.md; a rule signal, not a probability.
REASONS = {
    "model_output_invalid": HIGH,
    "inconsistent_decision_basis": HIGH,
    "met_without_verified_evidence": HIGH,
    "years_below_minimum_in_evidence": HIGH,
    "negation_in_evidence_context": HIGH,
    "certification_not_evidenced": HIGH,
    "contradiction_refuted_by_evidence": HIGH,
    "possible_prompt_injection": HIGH,
    "weak_evidence_cue": HIGH,
    "evidence_not_in_cv": MEDIUM,
    "evidence_too_short": MEDIUM,
    "contradiction_without_evidence": MEDIUM,
    "duration_not_verified": MEDIUM,
    "semantic_inference_no_term_in_quote": MEDIUM,
    "uncertain_decision": MEDIUM,
    "must_have_absence_of_evidence": MEDIUM,
    "must_have_contradicted": MEDIUM,
}


def parse_model_output(raw):
    """First JSON object in the raw generation, validated against ModelAnswer; None if impossible."""
    raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S)
    start = raw.find("{")
    while start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(raw[start:])
            return ModelAnswer.model_validate(obj)
        except (json.JSONDecodeError, ValidationError, TypeError):
            start = raw.find("{", start + 1)
    return None


def find_span(cv_text, quote):
    """[start, end) of an exact occurrence, or None. Only surrounding whitespace is stripped."""
    q = quote.strip()
    i = cv_text.find(q) if q else -1
    return (i, i + len(q)) if i >= 0 else None


_NEG = re.compile(r"\b(never|no|not|without|lacks?|lacking|none|nor|cannot)\b|n't\b", re.I)
_CERT = re.compile(r"certif|licen[cs]|accredit|credential", re.I)
_INJECT = re.compile(r"ignore\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)\s+instructions|^\W*system\s*:|"
                     r"mark\s+(every|all|each|this)\s+requirements?\s+(as\s+)?met", re.I | re.M)
_WEAK = re.compile(r"\b(tutorials?|watched|read (?:about|up on)|interested in|online course|bootcamp|familiar with|"
                   r"exposure to|introductory|attended (?:a |an )?(?:talk|webinar|workshop)|"
                   r"(?:preparing|studying) for|plans? to|enrolled in)\b", re.I)  # S2 cues: 0/305 train MET quotes
_CLAUSE = re.compile(r"[,;\n]|\.(?=\s|$)")
_SENT = re.compile(r"[;\n]|\.(?=\s|$)")


def _has_term(text, terms):
    return any(re.search(rf"(?<!\w){re.escape(t)}(?!\w)", text, re.I) for t in terms)


def line_context(cv_text, span):
    """CV text from the start of the span's line to the end of the span (what precedes the quote on its line)."""
    return cv_text[cv_text.rfind("\n", 0, span[0]) + 1:span[1]]


_YEARS = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", re.I)
_NUMWORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                         "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
_NUMWORD_YEARS = re.compile(rf"\b({'|'.join(_NUMWORDS)})(?=\s*\+?\s*(?:years?|yrs?)\b)", re.I)
_SINCE = re.compile(r"\bsince\s+((?:19|20)\d\d)\b", re.I)


def _norm_duration(q):
    """QA-032: 'Seven years' -> '7 years'; 'since 2018' -> '2018 - present' (read like a range to today)."""
    q = _NUMWORD_YEARS.sub(lambda m: str(_NUMWORDS[m.group(1).lower()]), q)
    return _SINCE.sub(lambda m: f"{m.group(1)} - present", q)


_RANGE = re.compile(r"\b((?:19|20)\d\d)\s*(?:-|–|—|to)\s*((?:19|20)\d\d|present|now|current|today)\b", re.I)


def evidence_years(quotes, ref_year=2026, terms=None):
    """Largest of: explicit 'N years' mentions, merged span of year ranges. None if nothing parseable.
    With terms, only clauses naming a term count (years of another skill or another section do not)."""
    quotes = [_norm_duration(q) for q in quotes]
    if terms:
        scoped = []
        for sent in (x for q in quotes for x in _SENT.split(q) if _has_term(x, terms)):
            own = [c for c in _CLAUSE.split(sent) if _has_term(c, terms)]
            # QA-031: "Over the last 6 years, Airflow was ..." puts the duration in another clause of the same sentence
            scoped += own if any(_YEARS.search(c) or _RANGE.search(c) for c in own) else [sent]
        quotes = scoped
    explicit = [float(m) for q in quotes for m in _YEARS.findall(q)]
    ranges = sorted((int(a), ref_year if not b.isdigit() else int(b)) for q in quotes for a, b in _RANGE.findall(q))
    merged = []
    for a, b in ranges:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    total = sum(b - a for a, b in merged) if merged else None
    vals = explicit + ([total] if total is not None else [])
    return max(vals) if vals else None


def _terms(req, refs):
    """Requirement terms plus the names of retrieved concepts that ARE the required skill (a ref whose title or alias
    equals a skill term, or occurs in the requirement text). A merely related concept does not widen the set."""
    own = {t.casefold() for t in req.skill_terms}
    terms = list(req.skill_terms)
    for r in refs:
        names = [r.title, *r.aliases]
        if any(n.casefold() in own or _has_term(req.text, [n]) for n in names if len(n) >= 2):
            terms += names
    return {t.casefold() for t in terms if len(t) >= 2}


def validate(answer, cv, req, refs, ref_year=2026):
    reasons = []
    model_decision = answer.decision if answer else None
    if answer is None:
        decision, basis, quotes, expl = "UNCERTAIN", "ambiguous", [], "Model output was not valid JSON for the schema."
        reasons.append("model_output_invalid")
    else:
        decision, basis, expl = answer.decision, answer.basis, answer.explanation
        if basis not in CONSISTENT[decision]:
            decision, basis = "UNCERTAIN", "ambiguous"
            reasons.append("inconsistent_decision_basis")
        quotes = []
        for q in answer.evidence:
            span = find_span(cv.text, q)
            if span and sum(ch.isalnum() for ch in cv.text[span[0]:span[1]]) < 3:
                reasons.append("evidence_too_short")
            elif span:
                quotes.append(cv.text[span[0]:span[1]])
            else:
                reasons.append("evidence_not_in_cv")
    quotes = list(dict.fromkeys(quotes))
    spans = [find_span(cv.text, q) for q in quotes]

    if decision == "MET" and not quotes:
        decision, basis = "UNCERTAIN", "ambiguous"
        reasons.append("met_without_verified_evidence")
    if decision == "MISSING" and basis == "contradicted" and not quotes:
        basis = "not_documented"
        reasons.append("contradiction_without_evidence")
    terms = _terms(req, refs)
    if decision == "MET" and any(_NEG.search(line_context(cv.text, sp)) for sp in spans):
        reasons.append("negation_in_evidence_context")
    if decision == "MET" and quotes and all(_WEAK.search(q) for q in quotes):  # QA-025: exposure is not ability
        decision, basis = "UNCERTAIN", "ambiguous"
        reasons.append("weak_evidence_cue")
    if decision == "MET" and req.category == "certification" and not any(_CERT.search(q) for q in quotes):
        reasons.append("certification_not_evidenced")
    if _INJECT.search(cv.text):
        reasons.append("possible_prompt_injection")
    if decision == "MISSING" and basis == "contradicted" and req.min_years:
        years = evidence_years(quotes, ref_year, terms)
        if years is not None and years >= req.min_years:
            reasons.append("contradiction_refuted_by_evidence")
    if decision == "MET" and req.min_years:
        years = evidence_years(quotes, ref_year, terms)
        if years is None:  # QA-026: a minimum duration that the evidence does not state is not verified
            decision, basis = "UNCERTAIN", "ambiguous"
            reasons.append("duration_not_verified")
        elif years < req.min_years:
            decision, basis = "UNCERTAIN", "ambiguous"
            reasons.append("years_below_minimum_in_evidence")
    if decision == "MET" and req.category == "skill":
        if terms and not any(_has_term(q, terms) for q in quotes):
            reasons.append("semantic_inference_no_term_in_quote")
    if decision == "UNCERTAIN":
        reasons.append("uncertain_decision")
    if decision == "MISSING" and req.kind == "must":
        reasons.append("must_have_absence_of_evidence" if basis == "not_documented" else "must_have_contradicted")

    reasons = list(dict.fromkeys(reasons))
    prios = {REASONS[r] for r in reasons}
    priority = HIGH if HIGH in prios else MEDIUM if MEDIUM in prios else "low"
    return RequirementResult(
        req_id=req.req_id, requirement_text=req.text, kind=req.kind, decision=decision, basis=basis,
        evidence=quotes, evidence_spans=spans, explanation=expl, rag_refs=[r.source_id for r in refs],
        model_decision=model_decision, review_priority=priority, needs_human_review=priority != "low",
        review_reasons=reasons)
