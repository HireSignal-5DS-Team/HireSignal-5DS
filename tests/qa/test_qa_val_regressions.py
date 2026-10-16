"""Regression cases from the LIVE LoRA evaluation on val (claude/kind-albattani-k7qlt9 @ 46d24e1,
benchmark/results/qwen3-4b-q4+hslora-{none,rag}-val/predictions.jsonl). The model text below is the LoRA's raw
output copied verbatim from those runs and replayed through the current Validator / pipeline. The replay itself is
MOCK (no model runs here); the inputs are real model outputs. Analysis: docs/qa/analysis/val_error_analysis.md.
"""
import json
from pathlib import Path

import pytest
from _qa_support import Scripted, defect, explanation_on_topic, explanation_problems

from matcher import CV, Requirement
from matcher.pipeline import Pipeline
from matcher.validate import parse_model_output, validate

ROOT = Path(__file__).resolve().parents[2]
CASES = {c["case_id"]: c for c in map(json.loads, open(ROOT / "benchmark/data/val.jsonl"))}
TEMPLATE_MET = "The CV directly shows this requirement; the quote is copied from the CV."
TEMPLATES = (TEMPLATE_MET, "The CV shows this requirement is not met; the quote is copied from the CV.",
             "The CV only partly or indirectly addresses this requirement.", "The CV says nothing about this requirement.")


def lora_raw(quote):
    return json.dumps({"decision": "MET", "basis": "supported", "evidence": [quote], "explanation": TEMPLATE_MET})


def replay(case_id, req_id, raw):
    c = CASES[case_id]
    cv, req = CV(**c["cv"]), Requirement(**next(r for r in c["job"]["requirements"] if r["req_id"] == req_id))
    return validate(parse_model_output(raw), cv, req, []), req


# final false-MET: weak exposure quoted as MET -> validator gives an UNREVIEWED MET (the Judge flagged both, FAIL)
WEAK_EXPOSURE = [("val-029", "r4", "Watched tutorials about Angular in spare time."),   # both arms
                 ("val-017", "r1", "Watched tutorials about React in spare time.")]     # LoRA + RAG arm
# final false-MET: duration not stated -> MET kept with duration_not_verified (reviewed, but counted as false-MET)
NO_DURATION = [("val-009", "r3", "Applied Node.js in various side projects over time."),
               ("val-016", "r1", "Applied Angular in various side projects over time.")]  # base model too
# raw false-MET caught by the validator: years below minimum -> UNCERTAIN (gold MISSING/contradicted)
YEARS_BELOW = [("val-014", "r2", "Node.js in daily use for 3 years."), ("val-024", "r6", "React in daily use for 1 year."),
               ("val-028", "r4", "Vue.js in daily use for 1 year."), ("val-037", "r2", "React in daily use for 2 years.")]


def test_gold_labels_are_not_met():
    for cid, rid, _ in WEAK_EXPOSURE + NO_DURATION + YEARS_BELOW:
        assert CASES[cid]["gold"][rid]["decision"] != "MET"


@pytest.mark.parametrize("cid,rid,quote", YEARS_BELOW, ids=[f"{c}/{r}" for c, r, _ in YEARS_BELOW])
def test_lora_met_with_years_below_minimum_is_caught(cid, rid, quote):
    res, _ = replay(cid, rid, lora_raw(quote))
    assert res.decision == "UNCERTAIN" and res.model_decision == "MET" and res.needs_human_review
    assert "years_below_minimum_in_evidence" in res.review_reasons


@defect("QA-025", "S6")
@pytest.mark.parametrize("cid,rid,quote", WEAK_EXPOSURE, ids=[f"{c}/{r}" for c, r, _ in WEAK_EXPOSURE])
def test_weak_exposure_quote_is_not_an_unreviewed_met(cid, rid, quote):
    res, _ = replay(cid, rid, lora_raw(quote))
    assert res.decision != "MET" or res.needs_human_review


@defect("QA-026", "S6")
@pytest.mark.parametrize("cid,rid,quote", NO_DURATION, ids=[f"{c}/{r}" for c, r, _ in NO_DURATION])
def test_min_years_without_any_duration_is_not_met(cid, rid, quote):
    res, _ = replay(cid, rid, lora_raw(quote))
    assert "duration_not_verified" in res.review_reasons  # reviewed today ...
    assert res.decision != "MET"  # ... but the requirement is unverifiable: gold is UNCERTAIN/ambiguous


# ---- explanations (QA-028) --------------------------------------------------------------------------------------
def test_explanation_checker_negative_and_positive_controls():
    req = Requirement(req_id="r", text="Working knowledge of Angular", skill_terms=["Angular"])
    assert not any(explanation_on_topic(t, req) for t in TEMPLATES)
    base_like = "The CV mentions only watching Angular tutorials, which does not show working knowledge."
    assert explanation_on_topic(base_like, req)
    assert explanation_problems({"explanation": "Uses Angular for 9 years.", "evidence": ["Angular since 2020"]}, req)


@defect("QA-028", "S2")
def test_final_report_explanations_are_requirement_specific_and_grounded():
    """The LoRA emits 4 fixed templates (on-topic 0.000 on val vs 1.000 for the base model by this check). Whatever
    the model emits, each row of the final report must explain THIS requirement with THIS evidence."""
    c = CASES["val-000"]
    cv, job = c["cv"], c["job"]

    def lora_like(task):  # the LoRA's real behaviour: correct-looking decision, template explanation
        return json.dumps({"decision": "MISSING", "basis": "not_documented", "evidence": [],
                           "explanation": TEMPLATES[3]})
    out = Pipeline(Scripted(fn=lora_like), _NoRefs()).run(cv, job)
    reqs = {r["req_id"]: r for r in job["requirements"]}
    problems = {r["req_id"]: explanation_problems(r, reqs[r["req_id"]]) for r in out["requirements"]}
    assert all(not p for p in problems.values()), problems


class _NoRefs:
    name = "none"

    def lookup(self, req, k=3, job_id=None):
        return []
