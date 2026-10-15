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
    "negation_in_evidence": HIGH,
    "years_not_tied_to_skill": HIGH,
    "evidence_not_in_cv": MEDIUM,
    "evidence_too_short": MEDIUM,
    "no_requirement_term_in_quote": MEDIUM,
    "contradiction_without_evidence": MEDIUM,
    "duration_not_verified": HIGH,
    "semantic_inference_no_term_in_quote": MEDIUM,
    "uncertain_decision": MEDIUM,
    "must_have_absence_of_evidence": MEDIUM,
    "must_have_contradicted": MEDIUM,
}


def _normalize(obj):
    """Deterministic repair of harmless deviations: decision/basis case, extra keys dropped, a bare string quote listed,
    quotes capped at 3, explanation capped at 600 chars. Decision/basis are never repaired."""
    if not isinstance(obj, dict):
        return obj
    obj = {k: obj[k] for k in ModelAnswer.model_fields if k in obj}
    for k, f in (("decision", str.upper), ("basis", str.lower)):  # case only; values are never remapped
        if isinstance(obj.get(k), str):
            obj[k] = f(obj[k].strip())
    ev = obj.get("evidence", [])
    obj["evidence"] = ([ev] if isinstance(ev, str) else ev)[:3] if isinstance(ev, (str, list)) else ev
    if isinstance(obj.get("explanation"), str):
        obj["explanation"] = obj["explanation"][:600]
    obj.setdefault("explanation", "")
    return obj


def parse_model_output(raw):
    """First JSON object in the raw generation, validated against ModelAnswer; None if impossible."""
    raw = re.sub(r"<think>.*?(?:</think>|$)", "", raw or "", flags=re.S)  # unclosed block = no answer
    start = raw.find("{")
    while start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(raw[start:])
            return ModelAnswer.model_validate(_normalize(obj))
        except (json.JSONDecodeError, ValidationError, TypeError):
            start = raw.find("{", start + 1)
    return None


def find_span(cv_text, quote):
    """[start, end) of the quote in the CV, or None. Exact match first; else ignoring case and whitespace runs.
    The caller always stores cv_text[start:end], so stored evidence is verbatim CV text either way."""
    q = quote.strip()
    if not q:
        return None
    i = cv_text.find(q)
    if i >= 0:
        return i, i + len(q)
    m = re.search(r"\s+".join(map(re.escape, q.split())), cv_text, re.I)
    return (m.start(), m.end()) if m else None


_YEARS = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", re.I)
# year granularity; an optional month ("Jun 2021", "05/2021") may precede the end year
_RANGE = re.compile(r"\b((?:19|20)\d\d)\s*(?:-|–|—|to)\s*(?:[a-z]{3,9}\.?\s+|\d{1,2}/)?"
                    r"((?:19|20)\d\d|present|now|current|today)\b", re.I)


_SINCE = re.compile(r"\bsince\s+(?:[a-z]{3,9}\.?\s+)?((?:19|20)\d\d)\b", re.I)


def evidence_years(quotes, ref_year=2026):
    """Largest of: explicit 'N years' mentions, merged span of year ranges. None if nothing parseable."""
    explicit = [float(m) for q in quotes for m in _YEARS.findall(q)]
    ranges = sorted([(int(a), ref_year if not b.isdigit() else int(b)) for q in quotes for a, b in _RANGE.findall(q)]
                    + [(int(a), ref_year) for q in quotes for a in _SINCE.findall(q)])
    merged = []
    for a, b in ranges:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    total = sum(b - a for a, b in merged) if merged else None
    vals = explicit + ([total] if total is not None else [])
    return max(vals) if vals else None


_STOP = set("""a an and or of in on with for to the as at by be is are have has from years year experience
plus least minimum strong good solid working knowledge ability hands proven required preferred must nice""".split())
# shortcut: negation is lexical, so "zero-downtime" style phrases may demote a valid MET to UNCERTAIN (review, not loss)
_NEG = re.compile(r"\b(?:no|not|never|without|lacks?|none)\b|in preparation|expired|studying for|currently learning|planned",
                  re.I)


def _has(term, text):
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text.casefold()) is not None


def _terms(req, refs):
    """Requirement skill terms plus aliases of refs that name one of them (an unrelated retrieved ref adds nothing)."""
    terms = {t.casefold() for t in req.skill_terms if len(t) >= 2}
    for r in refs:
        names = {n.casefold() for n in [r.title, *r.aliases]}
        if any(_has(t, n) or _has(n, t) for t in terms for n in names):
            terms |= {n for n in names if len(n) >= 2}
    return terms


def _req_words(req):
    return {w for w in re.findall(r"[a-z][a-z0-9+#.]*", req.text.casefold()) if len(w) >= 3 and w not in _STOP}


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
            if span and span[1] - span[0] < 4:  # "e", "-", "CV": verbatim but proves nothing
                reasons.append("evidence_too_short")
            elif span:
                quotes.append(cv.text[span[0]:span[1]])
            else:
                reasons.append("evidence_not_in_cv")
    quotes = list(dict.fromkeys(quotes))
    spans = [find_span(cv.text, q) for q in quotes]
    terms = _terms(req, refs)

    if decision == "MET" and not quotes:
        decision, basis = "UNCERTAIN", "ambiguous"
        reasons.append("met_without_verified_evidence")
    if decision == "MISSING" and basis == "contradicted" and not quotes:
        basis = "not_documented"
        reasons.append("contradiction_without_evidence")
    if decision == "MET" and any(_NEG.search(q) for q in quotes):
        decision, basis = "UNCERTAIN", "ambiguous"
        reasons.append("negation_in_evidence")
    if decision == "MET" and req.min_years:
        # years must come from a quote that names the skill; other skills' or total-career years do not count
        # shortcut: attribution is per quote, so "Java (5 years), Python" credits Python; needs clause parsing to fix
        named = [i for i, q in enumerate(quotes) if any(_has(t, q) for t in terms)]
        if named:  # plus a role header ending <= 300 chars before a quote that names the skill
            about = [q for i, q in enumerate(quotes) if i in named or any(
                0 <= spans[j][0] - spans[i][1] <= 300 for j in named)]
        else:  # possible equivalence claim ("LAN/WAN" for networking): keep, but a human must confirm
            about = quotes
            reasons.append("years_not_tied_to_skill")
        years = evidence_years(about, ref_year)
        if years is None:  # the minimum cannot be confirmed from the quotes, so MET is not defensible
            decision, basis = "UNCERTAIN", "ambiguous"
            reasons.append("duration_not_verified")
        elif years < req.min_years:
            decision, basis = "UNCERTAIN", "ambiguous"
            reasons.append("years_below_minimum_in_evidence")
    if decision == "MET":
        if req.category == "skill" and terms:
            if not any(_has(t, q) for q in quotes for t in terms):
                reasons.append("semantic_inference_no_term_in_quote")
        elif not any(_has(w, q) for q in quotes for w in _req_words(req) | terms):
            reasons.append("no_requirement_term_in_quote")
    if decision == "UNCERTAIN":
        reasons.append("uncertain_decision")
    if decision == "MISSING" and req.kind == "must":
        reasons.append("must_have_absence_of_evidence" if basis == "not_documented" else "must_have_contradicted")

    reasons = list(dict.fromkeys(reasons))
    if answer is not None and decision != model_decision:  # the model's explanation argued for another decision
        expl = f"Validator changed {model_decision} to {decision}: {', '.join(r for r in reasons if r != 'uncertain_decision')}."
    prios = {REASONS[r] for r in reasons}
    priority = HIGH if HIGH in prios else MEDIUM if MEDIUM in prios else "low"
    return RequirementResult(
        req_id=req.req_id, requirement_text=req.text, kind=req.kind, decision=decision, basis=basis,
        evidence=quotes, evidence_spans=spans, explanation=expl, rag_refs=[r.source_id for r in refs],
        model_decision=model_decision, review_priority=priority, needs_human_review=priority != "low",
        review_reasons=reasons)
