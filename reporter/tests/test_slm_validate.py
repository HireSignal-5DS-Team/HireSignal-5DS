"""Validator: hallucinated skills, numbers, quotes, employers, verdicts and wrong decisions are all rejected."""
import json

import pytest

from reporter.build import facts_for_requirement, facts_for_summary
from reporter.slm_validate import validate

from _fixtures import pipeline_output

OUT = pipeline_output()
F = {r["req_id"]: facts_for_requirement(r) for r in OUT["requirements"]}
S = facts_for_summary(OUT)


def note(t):
    return json.dumps({"note": t})


def summ(t):
    return json.dumps({"summary": t})


@pytest.mark.parametrize("rid,text", [
    ("r1", 'MET: the CV states "5 years of professional Python experience."'),
    ("r1", "MET: the CV shows 5 years of Python experience."),
    ("r2", 'MISSING: the CV states "Has not worked with Kubernetes so far.", which does not meet the requirement; '
           "a human reviewer must check it."),
    ("r3", "MISSING: the CV does not mention Terraform, which is not proof that it is absent; a human reviewer must "
           "check it."),
    ("r4", "UNCERTAIN: the evidence about Docker is partial."),
])
def test_faithful_notes_are_accepted(rid, text):
    assert validate(note(text), F[rid], "note") == (text, [])


@pytest.mark.parametrize("rid,text,reason", [
    ("r1", "MET: the CV shows 5 years of Python and Django experience.", "term_not_in_facts:Django"),       # skill
    ("r1", "MET: the CV shows 7 years of Python experience.", "number_not_in_facts:7"),                  # number
    ("r1", "MET: the CV shows seven years of Python experience.", "number_not_in_facts:seven"),          # number word
    ("r1", "MET: the CV shows Python experience at Google.", "term_not_in_facts:Google"),                # employer
    ("r1", "MET: the CV shows a Python certification.", "term_not_in_facts:certification"),              # credential
    ("r1", 'MET: the CV states "8 years of professional Python experience."', "quote_not_in_facts"),     # quote
    ("r1", "MET: the CV shows Python experience, so we recommend hiring.", "hiring_verdict"),            # verdict
    ("r1", "MET: Python experience is shown; hire.", "hiring_verdict"),
    ("r2", "MISSING: Kubernetes experience is missing, reject the applicant.", "hiring_verdict"),
    ("r1", "MET: the candidate is a strong fit for Python.", "judgement_word"),                            # judgement
    ("r1", "MET: the candidate is qualified in Python.", "judgement_word"),
    ("r1", "MISSING: the CV shows Python experience.", "decision"),                                        # decision
    ("r1", "MET: the requirement is not met by the CV.", "decision_claim"),
    ("r2", "MET: the CV states Kubernetes.", "decision"),
    ("r3", "MISSING: the candidate lacks Terraform.", "judgement_word:lacks"),                             # QA-011
    ("r3", "MISSING: the CV does not meet the Terraform requirement.", "decision_claim:NOT_MET"),
    ("r2", "MISSING: the CV does not mention Kubernetes.", "decision_claim:NOT_DOCUMENTED"),
    ("r4", "UNCERTAIN: the requirement is met by the Docker course.", "decision_claim:MET"),
    ("r1", "MET: the CV states Python; a human reviewer must check it.", "review_claim_mismatch"),        # review
    ("r3", "MISSING: the CV does not mention Terraform; no review is needed.", "review_claim_mismatch"),
    ("r1", "MET: the evidence_quotes show Python.", "json_key_in_text"),
    ("r4", "UNCERTAIN: the CV does not provide evidence about Docker.", "decision_claim:NOT_DOCUMENTED"),
])
def test_hallucinated_notes_are_rejected(rid, text, reason):
    got, errs = validate(note(text), F[rid], "note")
    assert got is None and any(reason in e for e in errs), errs


@pytest.mark.parametrize("raw,reason", [
    ("not json", "invalid_json"), ('{"note": "MET"', "invalid_json"), ('{"summary": "MET: x y z w v"}', "wrong_schema"),
    ('{"note": "MET: ok.", "extra": 1}', "wrong_schema"), ('{"note": "MET"}', "length_out_of_range"),
    ('{"note": "MET: one. Two. Three. Four."}', "more_than_one_sentence"),
])
def test_malformed_output_is_rejected(raw, reason):
    assert validate(raw, F["r1"], "note") == (None, [reason])


def test_faithful_summary_is_accepted():
    t = ("Of 4 requirements, 1 is MET, 2 are MISSING and 1 is UNCERTAIN. 1 of 3 must-have requirements is MET. "
         "3 requirements need human review.")
    assert S["need_human_review"] == 3
    assert validate(summ(t), S, "summary") == (t, [])


@pytest.mark.parametrize("text,reason", [
    ("Of 4 requirements, 2 are MET, 1 is MISSING and 1 is UNCERTAIN.", "count_mismatch"),
    ("Of 5 requirements, 1 is MET.", "count_mismatch"),
    ("1 of 3 must-have requirements is MET and 1 must-have requirement is UNCERTAIN.", "count_mismatch"),
    ("2 of 3 must-have requirements are MET.", "count_mismatch"),
    ("No requirements are uncertain.", "count_mismatch"),
    ("No human review is needed for these 4 requirements.", "review_claim_mismatch"),
    ("1 requirement needs human review.", "count_mismatch"),
    ("Of 4 requirements, 1 is MET. The candidate is suitable for the role.", "judgement_word"),
    ("Of 4 requirements, 1 is MET. We recommend an interview.", "hiring_verdict"),
    ("Of 4 requirements, 1 is MET, including Python at 9 years.", "number_not_in_facts:9"),
    ("Of 4 requirements, 1 is MET; Kubernetes and AWS are MISSING.", "term_not_in_facts:AWS"),
    ("Of 4 requirements, all are MISSING.", "count_mismatch"),
    ("All must-have requirements are MET.", "count_mismatch"),
    ("All requirements need human review.", "count_mismatch"),
])
def test_hallucinated_summaries_are_rejected(text, reason):
    got, errs = validate(summ(text), S, "summary")
    assert got is None and any(reason in e for e in errs), errs
