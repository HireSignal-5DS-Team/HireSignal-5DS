"""Deterministic converters from a model's native output to the ModelAnswer JSON. They never add evidence,
explanations or judgments the model did not produce: anything they cannot map becomes UNCERTAIN, and every quote
still goes through the exact-substring check in matcher/validate.py afterwards.

- schema_repair: first JSON object; keys lower-cased; unknown keys dropped; decision labels mapped by a fixed table
  (misspellings / synonyms of the three labels); a label listing several options ("A|B|C", the template copied)
  is UNCERTAIN; an invalid basis is derived from the decision (MISSING -> contradicted only if a quote exists).
- kushal_native: Kus-hal/resume-screener-lora's trained format {"role","ats_score","verdict","matched_skills",
  "missing_skills","years_experience"}. Requirement-level mapping only through the requirement's own skill terms:
  term in missing_skills -> MISSING/not_documented; term in matched_skills -> MET with NO evidence (so validation
  turns it into UNCERTAIN unless the model also quoted the CV); otherwise UNCERTAIN. ats_score / verdict are
  whole-resume signals and are not used for a requirement decision.
"""
import json
import re

LABELS = {"MET": "MET", "MATCH": "MET", "MATCHED": "MET", "SATISFIED": "MET", "YES": "MET",
          "MISSING": "MISSING", "NOT_MET": "MISSING", "NOT MET": "MISSING", "NOT_DOCUMENTED": "MISSING",
          "NOT DOCUMENTED": "MISSING", "CONTRADICTED": "MISSING", "CONTRADIZED": "MISSING", "NO": "MISSING",
          "UNCERTAIN": "UNCERTAIN", "AMBIGUOUS": "UNCERTAIN", "UNKNOWN": "UNCERTAIN", "PARTIAL": "UNCERTAIN"}
BASES = {"supported", "contradicted", "not_documented", "ambiguous"}


def first_object(raw):
    start = (raw or "").find("{")
    while start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(raw[start:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        start = raw.find("{", start + 1)
    return None


def _answer(decision, basis, evidence, explanation):
    if decision == "MET":
        basis = "supported"
    elif decision == "UNCERTAIN":
        basis = "ambiguous"
    elif basis not in ("contradicted", "not_documented"):
        basis = "contradicted" if evidence else "not_documented"
    if basis == "not_documented":
        evidence = []
    return json.dumps({"decision": decision, "basis": basis, "evidence": evidence[:3],
                       "explanation": (explanation or "")[:600]})


def schema_repair(raw):
    obj = first_object(raw)
    if obj is None:
        return raw
    obj = {str(k).strip().lower(): v for k, v in obj.items()}
    label = str(obj.get("decision", "")).strip().upper()
    decision = "UNCERTAIN" if "|" in label else LABELS.get(label, "UNCERTAIN")
    if label == "NOT_DOCUMENTED" or label == "NOT DOCUMENTED":
        basis = "not_documented"
    elif label in ("CONTRADICTED", "CONTRADIZED"):
        basis = "contradicted"
    else:
        basis = str(obj.get("basis", "")).strip().lower()
        basis = basis if basis in BASES else ""
    ev = obj.get("evidence", [])
    ev = [e for e in (ev if isinstance(ev, list) else [ev]) if isinstance(e, str)]
    expl = obj.get("explanation")
    return _answer(decision, basis, ev, expl if isinstance(expl, str) else "")


def kushal_native(raw, skill_terms):
    obj = first_object(raw)
    if obj is None:
        return raw
    if "decision" in {str(k).lower() for k in obj}:  # the model answered in our schema: repair that instead
        return schema_repair(raw)
    norm = lambda xs: [str(x).casefold() for x in xs] if isinstance(xs, list) else []  # noqa: E731
    matched, missing = norm(obj.get("matched_skills")), norm(obj.get("missing_skills"))
    hit = lambda pool: any(t.casefold() in s or s in t.casefold() for t in skill_terms for s in pool if s)  # noqa: E731
    if hit(missing):
        return _answer("MISSING", "not_documented", [], "Listed in the model's missing_skills.")
    if hit(matched):
        return _answer("MET", "supported", [], "Listed in the model's matched_skills (no CV quote given).")
    return _answer("UNCERTAIN", "ambiguous", [], "The native verdict does not address this requirement.")


def detect_native(raw):
    obj = first_object(raw)
    return bool(obj) and bool({"verdict", "matched_skills", "missing_skills", "ats_score"} & {str(k).lower() for k in obj})


if __name__ == "__main__":
    assert json.loads(schema_repair('{"decision": "CONTRADIZED", "basis": "x", "evidence": ["a"], "Explanation": "e", "skills": []}')) == \
        {"decision": "MISSING", "basis": "contradicted", "evidence": ["a"], "explanation": "e"}
    assert json.loads(schema_repair('{"decision": "CHALLENGE|contradicted"}'))["decision"] == "UNCERTAIN"
    assert json.loads(schema_repair('{"decision": "NOT_DOCUMENTED", "evidence": ["q"]}'))["evidence"] == []
    n = '{"role": "x", "ats_score": 56, "verdict": "moderate_match", "matched_skills": ["Python"], "missing_skills": ["Redis"]}'
    assert json.loads(kushal_native(n, ["Redis"]))["decision"] == "MISSING"
    assert json.loads(kushal_native(n, ["Python"])) == {"decision": "MET", "basis": "supported", "evidence": [],
                                                        "explanation": "Listed in the model's matched_skills (no CV quote given)."}
    assert json.loads(kushal_native(n, ["Kafka"]))["decision"] == "UNCERTAIN"
    assert re.match(r"no json", kushal_native("no json", ["x"]))
    print("ok")
