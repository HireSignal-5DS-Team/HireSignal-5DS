"""Prompt variants used only for the Kus-hal adapter investigation (benchmark --prompt-variant). Default inference
uses matcher.prompt (p1) unchanged.

- p1_oneshot: p1 + one worked example. The example CV, skill and quote are invented here and appear in no split.
- kushal_native: the adapter's own training style (model card: "Screen this resume for a <role> position and
  return a structured verdict. Resume: ..."), one user message, no system prompt. Its output is converted with
  matcher.output_adapters.kushal_native.
"""
import json

from . import prompt

EXAMPLE_CV = "Profile\nSurveyor turned analyst.\n- Mapped 300 km of rural roads with QGIS for the regional council.\n- Hobby: beekeeping."
EXAMPLE_REQ = "Requirement (must-have, skill): Experience with QGIS"
EXAMPLE_ANSWER = json.dumps({"decision": "MET", "basis": "supported",
                             "evidence": ["Mapped 300 km of rural roads with QGIS for the regional council."],
                             "explanation": "The CV describes concrete QGIS work; the quote is copied from the CV."})


def messages(variant, cv, req, refs):
    if variant == "p1":
        return prompt.messages(cv, req, refs)
    if variant == "p1_oneshot":
        sys_msg, user = prompt.messages(cv, req, refs)
        shot = f"CV:\n<<<\n{EXAMPLE_CV}\n>>>\n\n{EXAMPLE_REQ}\n\nKnowledge (terminology only, not candidate evidence):\n(none retrieved)\n\nJSON:"
        return [sys_msg, {"role": "user", "content": shot}, {"role": "assistant", "content": EXAMPLE_ANSWER}, user]
    if variant == "kushal_native":
        years = f" (minimum {req.min_years:g} years)" if req.min_years else ""
        return [{"role": "user", "content": f"Screen this resume for a position requiring: {req.text}{years}. "
                                            f"Return a structured verdict. Resume: {cv.text}"}]
    raise ValueError(f"unknown prompt variant {variant!r}")
