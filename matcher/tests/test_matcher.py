import json
import os
from pathlib import Path

import pytest

from matcher import CV, Job, Matcher, MatchReport, Requirement
from matcher.backends import LexicalBaseline, MockBackend
from matcher.knowledge import FixtureKnowledge, NoKnowledge, esco_aliases
from matcher.prompt import messages
from matcher.validate import evidence_years, parse_model_output, validate

CV_TEXT = """Profile
Data analyst with 4 years of experience in SQL reporting (2021 - 2025).
Built a churn prediction model with gradient boosting for a telecom client.
Did not use Kubernetes in production.
Hobbies: chess, hiking."""
CVX = CV(cv_id="cv-1", text=CV_TEXT)
FIX = FixtureKnowledge([{"source_id": "esco:sql", "title": "SQL", "aliases": ["structured query language"],
                         "text": "SQL. Also known as: structured query language. A query language."}])


def req(**kw):
    return Requirement(**{"req_id": "r1", "text": "SQL", "skill_terms": ["SQL"], **kw})


def ans(**kw):
    return json.dumps({"decision": "MET", "basis": "supported", "evidence": [], "explanation": "x", **kw})


def run(raw, r=None, refs=()):
    return validate(parse_model_output(raw), CVX, r or req(), list(refs))


def test_verified_quote_keeps_met_with_span():
    q = "4 years of experience in SQL reporting"
    out = run(ans(evidence=[q]))
    assert out.decision == "MET" and out.evidence == [q] and not out.needs_human_review
    s, e = out.evidence_spans[0]
    assert CV_TEXT[s:e] == q


def test_fabricated_quote_downgrades_met():
    out = run(ans(evidence=["10 years of SQL at Google"]))
    assert out.decision == "UNCERTAIN" and out.evidence == []
    assert {"evidence_not_in_cv", "met_without_verified_evidence"} <= set(out.review_reasons)
    assert out.review_priority == "high" and out.model_decision == "MET"


def test_invalid_json_becomes_uncertain():
    out = run("I think the candidate is great!")
    assert out.decision == "UNCERTAIN" and out.model_decision is None and "model_output_invalid" in out.review_reasons


def test_json_inside_noise_and_think_block_parsed():
    raw = "<think>{\"decision\": \"MET\"}</think>Sure: ```json\n" + ans(decision="UNCERTAIN", basis="ambiguous") + "\n```"
    assert parse_model_output(raw).decision == "UNCERTAIN"


def test_inconsistent_basis_rejected():
    out = run(ans(decision="MET", basis="not_documented", evidence=["Data analyst"]))
    assert out.decision == "UNCERTAIN" and "inconsistent_decision_basis" in out.review_reasons


def test_years_below_minimum_blocks_met():
    q = "4 years of experience in SQL reporting"
    out = run(ans(evidence=[q]), req(category="experience", min_years=5))
    assert out.decision == "UNCERTAIN" and "years_below_minimum_in_evidence" in out.review_reasons
    assert run(ans(evidence=[q]), req(category="experience", min_years=3)).decision == "MET"


def test_evidence_years():
    assert evidence_years(["4 years of SQL"]) == 4
    assert evidence_years(["2018 - 2020", "2019 to present"], ref_year=2026) == 8  # overlap merged
    assert evidence_years(["several projects"]) is None
    assert evidence_years(["Mar 2018 – Jun 2021 Python developer"]) == 3
    assert evidence_years(["03/2017 - 05/2020"]) == 3
    assert evidence_years(["Since 2017 I have designed workloads on Azure"], ref_year=2026) == 9


def test_contradiction_without_quote_is_not_documented():
    out = run(ans(decision="MISSING", basis="contradicted"))
    assert out.basis == "not_documented" and "contradiction_without_evidence" in out.review_reasons


def test_missing_must_have_flagged_for_review_but_nice_not():
    raw = ans(decision="MISSING", basis="not_documented")
    assert run(raw, req(kind="must")).needs_human_review
    assert not run(raw, req(kind="nice")).needs_human_review


def test_semantic_met_without_term_needs_review():
    q = "Built a churn prediction model with gradient boosting for a telecom client."
    out = run(ans(evidence=[q]), req(text="machine learning", skill_terms=["machine learning"]))
    assert out.decision == "MET" and "semantic_inference_no_term_in_quote" in out.review_reasons


def test_knowledge_text_cannot_be_evidence():
    refs = FIX.lookup(req())
    out = run(ans(evidence=[refs[0].text]), refs=refs)  # quoting ESCO, not the CV
    assert out.decision == "UNCERTAIN" and out.rag_refs == ["esco:sql"]


def test_prompt_separates_knowledge_from_cv():
    msgs = messages(CVX, req(), FIX.lookup(req()))
    assert "NOT evidence" in msgs[0]["content"] and "terminology only" in msgs[1]["content"]
    assert CV_TEXT in msgs[1]["content"]


def test_esco_aliases():
    assert esco_aliases("show initiative. Also known as: take the initiative; give impetus. Be proactive.") == \
        ["take the initiative", "give impetus"]


def test_lexical_baseline_negation_trap_and_alias():
    m = Matcher(LexicalBaseline(), FIX)
    k8s, _ = m.match_requirement(CVX, req(text="Kubernetes", skill_terms=["Kubernetes"]))
    assert k8s.model_decision == "MET"  # keyword matching falls for the negation...
    assert k8s.decision == "UNCERTAIN" and "negation_in_evidence" in k8s.review_reasons  # ...the validator does not
    cv2 = CV(cv_id="c2", text="Wrote Structured Query Language reports.")
    assert m.match_requirement(cv2, req())[0].decision == "MET"
    assert m.match_requirement(CV(cv_id="c3", text="Java developer."), req())[0].basis == "not_documented"


def test_report_is_schema_valid_and_never_rejects():
    job = Job(job_id="j1", title="Analyst", requirements=[req(), req(req_id="r2", text="Kafka", skill_terms=["Kafka"])])
    rep = Matcher(MockBackend(lambda t: ans(decision="UNCERTAIN", basis="ambiguous"), label="always-uncertain"),
                  NoKnowledge()).match(CVX, job)
    MatchReport.model_validate_json(rep.model_dump_json())
    assert rep.summary.counts == {"MET": 0, "MISSING": 0, "UNCERTAIN": 2}
    assert rep.backend["is_model"] is False and "No automatic rejection" in rep.summary.note


RAG_DIR = os.environ.get("HIRESIGNAL_RAG_DIR") or str(Path(__file__).parents[2] / "rag")


@pytest.mark.skipif(not Path(RAG_DIR, "retrieval.py").exists(), reason="RAG code not available (set HIRESIGNAL_RAG_DIR)")
def test_end_to_end_with_real_rag_bm25_and_mock_slm():
    """Structured CV -> job requirements -> team RAG (BM25 over ESCO) -> MOCK SLM -> validation -> JSON.
    The SLM is a MOCK here (weights not downloadable in this environment); RAG retrieval is real."""
    from matcher.knowledge import RagKnowledge

    rag = RagKnowledge(RAG_DIR)
    r = req(text="Experience with SQL databases", skill_terms=["SQL"])
    refs = rag.lookup(r)
    assert refs and all(x.source_type == "esco" and x.source_id.startswith("http://data.europa.eu/esco/") for x in refs)
    assert any("SQL" in x.title for x in refs)
    job = Job(job_id="j1", title="Analyst", requirements=[r])
    mock = MockBackend(lambda t: ans(evidence=["4 years of experience in SQL reporting"]), label="scripted-met")
    rep = Matcher(mock, rag).match(CVX, job)
    res = rep.results[0]
    assert res.decision == "MET" and res.rag_refs == [x.source_id for x in refs]
    assert json.loads(rep.model_dump_json())["backend"]["knowledge"] == "rag.bm25"


def test_met_with_unverifiable_duration_becomes_uncertain():
    out = run(ans(evidence=["Data analyst"]), req(category="experience", min_years=3))
    assert out.decision == "UNCERTAIN" and "duration_not_verified" in out.review_reasons


def test_harmless_json_deviations_repaired():
    raw = ('{"decision": "MET", "basis": "supported", "evidence": "Data analyst", "confidence": 0.9, '
           '"explanation": "' + "x" * 900 + '"}')
    a = parse_model_output(raw)
    assert a.evidence == ["Data analyst"] and len(a.explanation) == 600
    assert parse_model_output('{"decision": "MET", "basis": "supported", "evidence": ["a","b","c","d"]}').evidence == ["a", "b", "c"]
    assert parse_model_output('{"decision": "missing", "basis": "NOT_DOCUMENTED", "evidence": []}').basis == "not_documented"


def test_trivial_or_irrelevant_quote_flagged():
    out = run(ans(evidence=["e"]), req(text="MSc in Computer Science", category="education", skill_terms=[]))
    assert out.decision == "UNCERTAIN" and "evidence_too_short" in out.review_reasons
    out = run(ans(evidence=["Hobbies: chess, hiking."]), req(text="Fluent French", category="language", skill_terms=[]))
    assert out.decision == "MET" and out.needs_human_review and "no_requirement_term_in_quote" in out.review_reasons


def test_years_from_other_skill_do_not_count():
    cv = CV(cv_id="c", text="Java (5 years), Python\nBSc 2008-2012")
    r = Requirement(req_id="r", text="3+ years Python", skill_terms=["Python"], min_years=3)
    for ev in (["Python", "BSc 2008-2012"], ["BSc 2008-2012"]):
        a = parse_model_output(ans(evidence=ev))
        out = validate(a, cv, r, [])
        assert out.decision != "MET" or out.review_priority == "high"


def test_unrelated_ref_alias_does_not_silence_semantic_flag():
    from matcher.schemas import KnowledgeRef
    java = KnowledgeRef(source_type="esco", source_id="esco:java", title="Java (computer programming)", text="Java.",
                        aliases=["J2EE"], retrieval="test")
    cv = CV(cv_id="c", text="Backend work in J2EE since 2015.")
    out = validate(parse_model_output(ans(evidence=["Backend work in J2EE since 2015."])), cv,
                   Requirement(req_id="r", text="Kotlin", skill_terms=["Kotlin"]), [java])
    assert "semantic_inference_no_term_in_quote" in out.review_reasons


def test_demoted_decision_replaces_model_explanation():
    out = run(ans(evidence=["Did not use Kubernetes in production."], explanation="Kubernetes is met."),
              req(text="Kubernetes", skill_terms=["Kubernetes"]))
    assert out.decision == "UNCERTAIN" and "met" not in out.explanation.split(":")[-1].lower().split()


def test_unclosed_think_block_is_not_an_answer():
    assert parse_model_output('<think>maybe {"decision": "MET", "basis": "supported", "evidence": []}') is None


def test_quote_located_case_insensitively_but_stored_verbatim():
    out = run(ans(evidence=["built a churn  prediction model"]), req(text="churn prediction", skill_terms=["churn"]))
    assert out.decision == "MET" and out.evidence == ["Built a churn prediction model"]
    s, e = out.evidence_spans[0]
    assert CV_TEXT[s:e] == out.evidence[0]
