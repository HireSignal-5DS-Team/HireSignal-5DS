"""Evidence grounding and false-MET traps for the deterministic Validator (matcher/validate.py, owner S6).

MOCK: the "model" is a scripted answer. These tests check what the Validator does with an adversarial or mistaken
answer; whether the live models produce such answers is measured by tests/live/.

Convention: a test that is not marked `defect(...)` pins behaviour that is correct today.
"""
import pytest
from _qa_support import CVX, check, ref, req

from matcher import CV
from matcher.validate import find_span

K8S = req("r3", "Hands-on Kubernetes experience", skill_terms=["Kubernetes"])
KAFKA = req("r4", "Experience with Apache Kafka", skill_terms=["Kafka"])
PY5 = req("r1", "At least 5 years of Python", category="experience", skill_terms=["Python"], min_years=5)


# ---- grounding: what counts as a verbatim quote -----------------------------------------------------------------
@pytest.mark.parametrize("quote", [
    "Senior Python developer with 10 years at a bank.",              # fabricated
    "Senior Python engineer at a fintech scale-up (2019 - present).",  # paraphrased (one word)
    "senior python developer at a fintech scale-up (2019 - present).",  # case changed
    "Senior Python developer  at a fintech scale-up",                 # doubled internal space
    "Senior Python developer at a fintech scale-up",             # NBSP instead of space
    "Senior Py​thon developer at a fintech scale-up",            # zero-width space inserted
    "Senior Pythоn developer at a fintech scale-up",                  # Cyrillic 'о' homoglyph
    "Senior Python developer at a fintech scale-up (2019 - present).\n- Led a team of 40",  # starts in CV, runs out
    "",
    "   ",
])
def test_non_verbatim_quote_never_supports_met(quote):
    r = check("MET", "supported", [quote], CVX, PY5)
    assert r.decision == "UNCERTAIN" and r.evidence == [] and r.needs_human_review
    assert r.model_decision == "MET" and r.review_priority == "high"


def test_surrounding_whitespace_is_the_only_tolerance():
    r = check("MET", "supported", ["  Set up Maven builds for twelve Java services.\n"], CVX,
              req("r2", "Maven", skill_terms=["Maven"]))
    assert r.decision == "MET" and r.evidence == ["Set up Maven builds for twelve Java services."]
    a, b = r.evidence_spans[0]
    assert CVX.text[a:b] == r.evidence[0]


def test_mixed_real_and_fabricated_quotes_keep_only_verified_and_flag():
    r = check("MET", "supported", ["Set up Maven builds for twelve Java services.", "Maven certified expert."], CVX,
              req("r2", "Maven", skill_terms=["Maven"]))
    assert r.evidence == ["Set up Maven builds for twelve Java services."]
    assert "evidence_not_in_cv" in r.review_reasons and r.needs_human_review


def test_unicode_normalisation_is_not_applied_silently():
    cv = CV(cv_id="u", text="Expert in Kubernetés.")  # combining accent: NFD
    assert find_span(cv.text, "Expert in Kubernetés.") is None  # NFC form is a different string: rejected, not guessed


def test_duplicate_quotes_are_deduplicated_with_one_span():
    q = "Set up Maven builds for twelve Java services."
    r = check("MET", "supported", [q, q], CVX, req("r2", "Maven", skill_terms=["Maven"]))
    assert r.evidence == [q] and len(r.evidence_spans) == 1


def test_trivial_quote_is_not_evidence():
    lead = req("r9", "Experience leading engineering teams", category="experience")
    r = check("MET", "supported", ["e"], CVX, lead)  # 'e' is a substring of the CV, but proves nothing
    assert r.decision != "MET" or r.needs_human_review


def test_quote_stitched_across_sections_does_not_create_years():
    cv = CV(cv_id="s", text="Skills\n- Python\n\nHobbies\n- 10 years of competitive chess")
    r = check("MET", "supported", ["Python\n\nHobbies\n- 10 years"], cv, PY5)
    assert r.needs_human_review  # 10 years belong to chess, not Python


# ---- false-MET traps --------------------------------------------------------------------------------------------
def test_partial_quote_that_drops_a_negation_is_flagged():
    # CV: "Never used Kubernetes in production; ..." -> model quotes only the tail
    r = check("MET", "supported", ["Kubernetes in production"], CVX, K8S)
    assert r.decision != "MET" or r.needs_human_review


def test_no_experience_with_x_is_not_met():
    r = check("MET", "supported", ["experience with Kafka"], CVX, KAFKA)  # CV: "No experience with Kafka so far."
    assert r.decision != "MET" or r.needs_human_review


def test_full_negated_quote_as_met_is_flagged_by_the_validator():
    # whole negated line, requirement term present: today only the Judge can catch it (see test_qa_judge.py)
    r = check("MET", "supported", ["No experience with Kafka so far."], CVX, KAFKA)
    assert r.decision != "MET" or r.needs_human_review


def test_related_but_different_skill_term_is_flagged():
    java = req("r5", "Java development", skill_terms=["Java"])
    r = check("MET", "supported", ["6 years of JavaScript development."], CVX, java)  # 'java' in 'javascript'
    assert "semantic_inference_no_term_in_quote" in r.review_reasons


def test_absent_skill_without_knowledge_is_flagged_as_inference():
    cv = CV(cv_id="d", text="Built container images with Docker for CI.")
    r = check("MET", "supported", ["Built container images with Docker for CI."], cv, K8S)
    assert "semantic_inference_no_term_in_quote" in r.review_reasons and r.needs_human_review


def test_related_esco_concept_in_rag_context_does_not_launder_absent_skill():
    cv = CV(cv_id="d", text="Built container images with Docker for CI.")
    docker = ref("esco/docker", "Docker", ["Docker Engine"], score=0.4)  # retrieved for "Kubernetes": related, not same
    r = check("MET", "supported", ["Built container images with Docker for CI."], cv, K8S, refs=[docker])
    assert r.needs_human_review


def test_alias_from_matching_esco_concept_is_accepted():
    maven = ref("esco/maven", "Apache Maven", ["Maven"])
    r = check("MET", "supported", ["Set up Maven builds for twelve Java services."], CVX,
              req("r2", "Experience with Apache Maven", skill_terms=["Apache Maven"]), refs=[maven])
    assert r.decision == "MET" and not r.needs_human_review


def test_course_is_not_a_required_certification():
    cert = req("r6", "AWS Certified Solutions Architect", category="certification",
               skill_terms=["AWS Solutions Architect"])
    r = check("MET", "supported", ["Completed an online course on AWS Solutions Architect topics."], CVX, cert)
    assert r.decision != "MET" or r.needs_human_review


def test_years_of_another_skill_do_not_satisfy_min_years():
    cv = CV(cv_id="y", text="- 2 years of Python, 10 years of Java.")
    r = check("MET", "supported", ["- 2 years of Python, 10 years of Java."], cv, PY5)
    assert r.decision != "MET" or r.needs_human_review


def test_years_below_minimum_downgrades_met():
    cv = CV(cv_id="y", text="- 3 years of Python.")
    r = check("MET", "supported", ["- 3 years of Python."], cv, PY5)
    assert r.decision == "UNCERTAIN" and "years_below_minimum_in_evidence" in r.review_reasons


def test_year_range_to_present_counts_and_unparseable_duration_is_flagged():
    r = check("MET", "supported", ["Senior Python developer at a fintech scale-up (2019 - present)."], CVX, PY5)
    assert r.decision == "MET" and not r.needs_human_review  # 2019 -> 2026 = 7 >= 5
    cv = CV(cv_id="y", text="- Five years of Python.")
    r = check("MET", "supported", ["- Five years of Python."], cv, PY5)
    assert "duration_not_verified" in r.review_reasons


def test_contradicted_claim_refuted_by_its_own_quote_is_flagged():
    nice = req("r7", "3 years of JavaScript", kind="nice", category="experience", skill_terms=["JavaScript"], min_years=3)
    r = check("MISSING", "contradicted", ["6 years of JavaScript development."], CVX, nice)
    assert r.needs_human_review  # the quote shows 6 >= 3 years: the 'contradiction' is wrong


def test_no_evidence_nice_to_have_is_missing_without_review_flag():
    """Decision on QA-011 (ORCHESTRATION §3.3): MISSING = not documented. Reviewed for must requirements only;
    a nice-to-have MISSING carries no review flag (and never rejects anyone)."""
    r = check("MISSING", "not_documented", [], CVX, KAFKA.model_copy(update={"kind": "nice"}))
    assert r.decision == "MISSING" and r.basis == "not_documented"
    assert not r.needs_human_review and r.review_reasons == []


def test_no_evidence_must_have_goes_to_review():
    r = check("MISSING", "not_documented", [], CVX, KAFKA)
    assert r.needs_human_review and "must_have_absence_of_evidence" in r.review_reasons


def test_inconsistent_decision_basis_is_uncertain():
    r = check("MET", "not_documented", ["Set up Maven builds for twelve Java services."], CVX, K8S)
    assert r.decision == "UNCERTAIN" and "inconsistent_decision_basis" in r.review_reasons


@pytest.mark.parametrize("quote,term,minimum", [("Node.js in daily use for 3 years.", "Node.js", 4),
                                                ("Vue.js in daily use for 1 year.", "Vue.js", 3)])
def test_years_with_a_dotted_skill_name_still_count(quote, term, minimum):
    """Regression from val (val-014/r2, val-028/r4): a clause splitter must not cut 'Node.js' at the dot."""
    cv = CV(cv_id="d", text=f"- {quote}")
    r = check("MET", "supported", [quote], cv,
              req("r1", f"{term}: {minimum} years", category="experience", skill_terms=[term], min_years=minimum))
    assert r.decision == "UNCERTAIN" and "years_below_minimum_in_evidence" in r.review_reasons
