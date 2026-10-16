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
- strict_repair: the production Matcher's repair, used only when matcher/validate.parse_model_output fails. It
  NEVER maps synonyms and never derives a decision or basis: the decision must be one of MET/MISSING/UNCERTAIN and
  the basis one of the four bases as the model wrote them (only case, spaces and hyphens are normalised). It fixes
  form only: code fences, a Python-literal dict, key case, extra keys, a string instead of a list of quotes, more
  than 3 quotes, an over-long or missing explanation, and output cut off by max_tokens inside the explanation
  (decision, basis and the complete evidence list must already be there). Every repair is listed; the Matcher routes
  any repaired answer to human review. Anything else -> None (the validator's UNCERTAIN + model_output_invalid).
"""
import ast
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


COSMETIC = {"think_block", "code_fence"}  # form-only wrappers, not counted as a repair of the answer
_KEYS = ("decision", "basis", "evidence", "explanation")
_TRUNC = re.compile(r'"decision"\s*:\s*"(?P<d>[^"]*)"\s*,\s*"basis"\s*:\s*"(?P<b>[^"]*)"\s*,\s*"evidence"\s*:\s*'
                    r'(?P<e>\[(?:[^\]"\\]|"(?:[^"\\]|\\.)*")*\])\s*,\s*"explanation"\s*:\s*"(?P<x>(?:[^"\\]|\\.)*)$', re.S)


def _object(text):
    """(dict, repairs) from the first JSON object, else a Python-literal dict, else a truncated p1 answer."""
    obj = first_object(text)
    if obj is not None:
        return obj, []
    i = text.find("{")
    if i == -1:
        return None, []
    j = text.rfind("}")
    if j > i:
        try:
            lit = ast.literal_eval(text[i:j + 1])
            if isinstance(lit, dict):
                return lit, ["python_literal"]
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            pass
    m = _TRUNC.search(re.sub(r"(?<!\\)\\$", "", text[i:].rstrip()))  # a cut can leave a lone escape char
    if m:
        try:
            ev = json.loads(m["e"])
            expl = json.loads('"' + m["x"] + '"')
        except json.JSONDecodeError:
            return None, []
        return {"decision": m["d"], "basis": m["b"], "evidence": ev, "explanation": expl + " [truncated]"}, \
            ["truncated_output"]
    return None, []


def strict_repair(raw):
    """-> (ModelAnswer | None, repairs). Never invents or re-labels a decision (see module docstring)."""
    from pydantic import ValidationError

    from .schemas import ModelAnswer

    text, repairs = raw or "", []
    if re.search(r"<think>.*?</think>", text, flags=re.S):
        text, _ = re.subn(r"<think>.*?</think>", "", text, flags=re.S)
        repairs.append("think_block")
    if "```" in text:
        text = re.sub(r"```(?:json|JSON)?", "", text)
        repairs.append("code_fence")
    obj, r = _object(text)
    repairs += r
    if obj is None:
        return None, repairs + ["no_json_object"]
    norm = {str(k).strip().lower(): v for k, v in obj.items()}
    if list(norm) != list(obj):
        repairs.append("key_case")
    if set(norm) - set(_KEYS):
        repairs.append("extra_keys_dropped")
    d, b = norm.get("decision"), norm.get("basis")
    if not isinstance(d, str) or not isinstance(b, str):
        return None, repairs + ["decision_or_basis_missing"]
    dn, bn = d.strip().upper(), re.sub(r"[\s-]+", "_", b.strip().lower())
    if dn not in ("MET", "MISSING", "UNCERTAIN"):
        return None, repairs + ["invalid_decision_label"]
    if bn not in BASES:
        return None, repairs + ["invalid_basis_label"]
    if (dn, bn) != (d, b):
        repairs.append("label_case")
    ev = norm.get("evidence", [])
    if isinstance(ev, str):
        ev = [ev] if ev.strip() else []
        repairs.append("evidence_coerced")
    if not isinstance(ev, list):
        return None, repairs + ["evidence_not_a_list"]
    quotes = [e for e in ev if isinstance(e, str)]
    if len(quotes) != len(ev):
        repairs.append("evidence_coerced")
    if len(quotes) > 3:
        quotes = quotes[:3]
        repairs.append("evidence_truncated")
    expl = norm.get("explanation")
    if expl is None:
        expl = ""
        repairs.append("explanation_missing")
    if not isinstance(expl, str):
        return None, repairs + ["explanation_not_a_string"]
    if len(expl) > 600:
        expl = expl[:600]
        repairs.append("explanation_truncated")
    try:
        return ModelAnswer(decision=dn, basis=bn, evidence=quotes, explanation=expl), repairs
    except ValidationError:
        return None, repairs + ["schema_invalid"]


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
