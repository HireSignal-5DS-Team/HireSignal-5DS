"""Prompt of the tiny SLM report writer (versioned; id + sha256 go into the report provenance).

The SLM only rephrases verified facts. It receives a JSON object of facts (decision, basis, verbatim quotes, counts)
and must return a JSON object with one text field. The few-shot examples are written from SYNTHETIC fixtures
(invented requirements and CV lines), never from val or test data.
"""
import hashlib
import json

PROMPT_ID = "reporter-slm-p1"

SYSTEM = (
    "You write short plain-language text for a requirement-check report. You are not a recruiter.\n"
    "Rules:\n"
    "- Use ONLY the facts in the input JSON. Do not add skills, tools, years, numbers, employers, degrees or sources.\n"
    "- Keep each decision word exactly as given (MET, MISSING or UNCERTAIN).\n"
    "- If you quote the CV, copy a quote from evidence_quotes word for word, in double quotes.\n"
    "- MISSING with basis not_documented means the CV does not mention it. It does not mean the person lacks it.\n"
    "- Never recommend, hire, reject, rank or judge the person. Talk about the CV text and the requirement only.\n"
    "- Reply with one JSON object and nothing else."
)

NOTE_TASK = 'Write ONE sentence about this requirement. Reply as {"note": "..."}.'
RETRY_NOTE = ("Your previous answer was rejected by the fact checker: {reasons}. Write a new answer. Use only words, "
              "numbers and quotes from the facts.")
SUMMARY_TASK = 'Write two or three sentences summarising these results. Reply as {"summary": "..."}.'

# Synthetic few-shot fixtures (not from the benchmark): an invented pastry-chef job and an invented CV.
_NOTE_SHOTS = [
    ({"requirement": "Experience with sourdough baking", "kind": "must-have", "decision": "MET", "basis": "supported",
      "evidence_quotes": ["Baked sourdough daily for a neighbourhood bakery."], "needs_human_review": False},
     {"note": 'MET: the CV states "Baked sourdough daily for a neighbourhood bakery."'}),
    ({"requirement": "At least 3 years of cake decorating", "kind": "must-have", "decision": "MISSING",
      "basis": "contradicted", "evidence_quotes": ["Cake decorating for 1 year."], "needs_human_review": True},
     {"note": 'MISSING: the CV states "Cake decorating for 1 year.", which does not meet the requirement; '
              'a human reviewer must check it.'}),
]
_SUMMARY_SHOT = (
    {"requirements_checked": 3, "MET": 2, "MISSING": 1, "UNCERTAIN": 0, "must_have_met": 1, "must_have_total": 2,
     "nice_to_have_total": 1, "need_human_review": 1,
     "requirements": [{"requirement": "Experience with sourdough baking", "kind": "must-have", "decision": "MET"},
                      {"requirement": "At least 3 years of cake decorating", "kind": "must-have",
                       "decision": "MISSING"},
                      {"requirement": "Latte art", "kind": "nice-to-have", "decision": "MET"}]},
    {"summary": "Of 3 requirements, 2 are MET, 1 is MISSING and 0 are UNCERTAIN. 1 of 2 must-have requirements is MET. "
                "1 requirement needs human review."},
)


def _dump(o):
    return json.dumps(o, ensure_ascii=False)


def messages(kind, facts, feedback=None):
    """Chat messages for one section. kind: 'note' | 'summary'. feedback: validator reasons of a rejected attempt
    (the retry is corrective: greedy decoding would otherwise repeat the same text)."""
    task = NOTE_TASK if kind == "note" else SUMMARY_TASK
    shots = _NOTE_SHOTS if kind == "note" else [_SUMMARY_SHOT]
    msgs = [{"role": "system", "content": SYSTEM}]
    for f, a in shots:
        msgs += [{"role": "user", "content": f"{task}\nFacts: {_dump(f)}"}, {"role": "assistant", "content": _dump(a)}]
    msgs.append({"role": "user", "content": f"{task}\nFacts: {_dump(facts)}"
                 + (f"\n{RETRY_NOTE.format(reasons=feedback)}" if feedback else "")})
    return msgs


def chatml(msgs):
    """Qwen3 chat template with enable_thinking=False, rendered by hand (equals the GGUF's Jinja template output for
    plain text messages; checked in reporter/tests/test_slm_real.py): the empty <think></think> block disables
    thinking mode, as the official template does for enable_thinking=False."""
    s = "".join(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in msgs)
    return s + "<|im_start|>assistant\n<think>\n\n</think>\n\n"


def prompt_sha256():
    blob = _dump({"id": PROMPT_ID, "system": SYSTEM, "note": NOTE_TASK, "summary": SUMMARY_TASK, "retry": RETRY_NOTE,
                  "shots": [_NOTE_SHOTS, _SUMMARY_SHOT]})
    return hashlib.sha256(blob.encode()).hexdigest()


OUTPUT_SCHEMA = {
    "note": {"type": "object", "properties": {"note": {"type": "string", "minLength": 10, "maxLength": 300}},
             "required": ["note"], "additionalProperties": False},
    "summary": {"type": "object", "properties": {"summary": {"type": "string", "minLength": 20, "maxLength": 600}},
                "required": ["summary"], "additionalProperties": False},
}
