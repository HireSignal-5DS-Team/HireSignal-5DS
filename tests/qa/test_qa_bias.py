"""Bias Auditor (matcher/bias_audit.py, owner S4). MOCK Matchers with known behaviour: a biased one must be caught,
unbiased ones (negative controls) must stay clean. Real flip rates of the LoRA Matcher are a window-1 measurement.
"""
import pytest
from _qa_support import CVX, GOOD, JOB, Scripted, ans, check, defect

from matcher import CV
from matcher.agent import Matcher
from matcher.backends import LexicalBaseline
from matcher.bias_audit import ATTRIBUTES, check_result, counterfactual, variant
from matcher.knowledge import NoKnowledge

PY = JOB.requirements[0]


def matcher_fn(backend):
    m = Matcher(backend, NoKnowledge())
    return lambda cv, r: m.match_requirement(cv, r)[0]


def sensitive_to(token):
    def fn(task):
        if token in task.cv.text:
            return ans("MISSING", "not_documented")
        return ans(*GOOD[task.req.req_id])
    return fn


@pytest.mark.parametrize("attr", list(ATTRIBUTES))
def test_flip_on_each_attribute_is_caught(attr):
    token = ATTRIBUTES[attr][1]  # value B of that attribute
    f = counterfactual(matcher_fn(Scripted(fn=sensitive_to(token))), CVX, PY)
    assert f.audit_status == "FLAGGED" and f.counterfactual_flip and f.requires_human_review
    assert f.affected_attribute == attr and f.details[attr] == {**f.details[attr], "A": "MET", "B": "MISSING", "flip": True}


@pytest.mark.parametrize("backend", [Scripted(), LexicalBaseline()], ids=["scripted-unbiased", "lexical"])
def test_negative_controls_are_clean(backend):
    for r in JOB.requirements:
        f = counterfactual(matcher_fn(backend), CVX, r)
        assert f.audit_status == "PASS" and f.counterfactual_flip is False and not f.requires_human_review


def test_variants_change_only_the_attribute_line():
    for attr in ATTRIBUTES:
        a, b = variant(CVX.text, attr, "A"), variant(CVX.text, attr, "B")
        assert a.split("\n", 1)[1] == b.split("\n", 1)[1] == CVX.text and a != b


def test_audit_never_changes_the_decision_it_audits():
    m = matcher_fn(Scripted(fn=sensitive_to("Tunisian")))
    before = m(CVX, PY)
    f = counterfactual(m, CVX, PY)
    assert f.audit_status == "FLAGGED" and m(CVX, PY).decision == before.decision == "MET"


def test_demographic_quote_and_leaky_explanation_are_flagged():
    cv = CV(cv_id="b", text=variant(CVX.text, "age_signal", "B"))
    r = check("MISSING", "contradicted", ["Year of birth: 1966"], cv, PY, expl="Born in 1966, likely too old to adapt.")
    f = check_result(r, cv.text)
    assert f.audit_status == "FLAGGED" and f.demographic_evidence and "old" in f.leakage_terms


def test_clean_explanation_on_cv_with_attribute_line_passes():
    cv = CV(cv_id="b", text=variant(CVX.text, "name_signal", "B"))
    r = check(*GOOD["r1"], cv, PY, expl="The CV shows Python since 2019, which is 7 years.")
    assert check_result(r, cv.text).audit_status == "PASS"


@defect("QA-020", "S4")
def test_job_relevant_word_old_is_not_a_demographic_leak():
    cv = CV(cv_id="b", text=variant(CVX.text + "\n- Maintained an old Perl codebase.", "name_signal", "A"))
    r = check(*GOOD["r1"], cv, PY, expl="Python since 2019; also maintained an old Perl codebase.")
    assert check_result(r, cv.text).audit_status == "PASS"


@defect("QA-016", "S4")
def test_counterfactual_with_unavailable_matcher_is_not_a_pass():
    """Both variants return the invalid-output UNCERTAIN: no comparison happened, so the audit must not say PASS."""
    f = counterfactual(matcher_fn(Scripted(mode="down")), CVX, PY)
    assert f.audit_status != "PASS"
