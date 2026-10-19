# Adapted from team V2: matcher/tests/test_matcher.py, matcher/tests/test_evidence_years.py (feature/agent-integration @ a5a03ff)
"""Matcher validator v1 (evidence rules only) and the /match station with a mocked llama-server."""
import json

import httpx
import pytest

from rag.bm25_esco import BM25EscoKnowledge
from services.matcher import matcher as matcher_mod
from services.matcher.prompt import parse_strict
from services.matcher.validate import evidence_years, find_span, validate

CV_TEXT = """Profile
Data analyst with 4 years of experience in SQL reporting (2021 - 2025).
Built a churn prediction model with gradient boosting for a telecom client.
Did not use Kubernetes in production.
Hobbies: chess, hiking."""


def req(**kw):
    return {"req_id": "r1", "text": "SQL", "kind": "must", "category": "skill", "skill_terms": ["SQL"],
            "min_years": None, **kw}


def ans(**kw):
    return json.dumps({"decision": "MET", "basis": "supported", "evidence": [], "explanation": "x", **kw})


def run(raw, r=None):
    return validate(parse_strict(raw), CV_TEXT, r or req(), ref_year=2026)


# ------------------------------------------------------------- V2 ports ---

def test_verified_quote_keeps_met_with_span():
    q = "4 years of experience in SQL reporting"
    out = run(ans(evidence=[q]))
    assert out["decision"] == "MET" and not out["needs_human_review"]
    e = out["evidence"][0]
    assert e["quote"] == q and CV_TEXT[e["start"]:e["end"]] == q


def test_fabricated_quote_downgrades_met():
    out = run(ans(evidence=["10 years of SQL at Google"]))
    assert out["decision"] == "UNCERTAIN" and out["evidence"] == []
    assert {"evidence_not_in_cv", "met_without_verified_evidence"} <= set(out["review_reasons"])
    assert out["model_decision"] == "MET" and out["needs_human_review"]


def test_invalid_json_becomes_uncertain():
    out = run("I think the candidate is great!")
    assert out["decision"] == "UNCERTAIN" and out["model_decision"] is None
    assert "model_output_invalid" in out["review_reasons"]


def test_inconsistent_basis_rejected():
    out = run(ans(decision="MET", basis="not_documented", evidence=["Data analyst"]))
    assert out["decision"] == "UNCERTAIN" and "inconsistent_decision_basis" in out["review_reasons"]


def test_years_below_minimum_blocks_met():
    q = "4 years of experience in SQL reporting"
    out = run(ans(evidence=[q]), req(category="experience", min_years=5))
    assert out["decision"] == "UNCERTAIN" and "years_below_minimum_in_evidence" in out["review_reasons"]
    ok = run(ans(evidence=[q]), req(category="experience", min_years=3))
    assert ok["decision"] == "MET" and ok["evidence_years"] == 4


def test_evidence_years():
    assert evidence_years(["4 years of SQL"]) == 4
    assert evidence_years(["2018 - 2020", "2019 to present"], ref_year=2026) == 8  # overlap merged
    assert evidence_years(["several projects"]) is None


def test_no_stated_duration_stays_unverified():  # V2 QA-026
    assert evidence_years(["Built side projects with React over time"]) is None


def test_contradiction_without_quote_is_not_documented():
    out = run(ans(decision="MISSING", basis="contradicted"))
    assert out["basis"] == "not_documented" and "contradiction_without_evidence" in out["review_reasons"]


def test_knowledge_text_cannot_be_evidence():
    ref = BM25EscoKnowledge().lookup(req(), k=1)[0]
    out = run(ans(evidence=[ref["text"][:80]]))  # quoting ESCO, not the CV
    assert out["decision"] == "UNCERTAIN" and "evidence_not_in_cv" in out["review_reasons"]


# ------------------------------------------------------------- new (T04) ---

@pytest.mark.parametrize("quote,years", [("Seven years of Python", 7), ("Python since 2018", 8),
                                          ("2019 - present", 7), ("3+ years with Airflow", 3)])
def test_duration_forms(quote, years):  # V2 QA-032 forms
    assert evidence_years([quote], ref_year=2026) == years


def test_met_with_min_years_but_no_years_in_quote_is_kept_and_flagged():
    """V2 v2 downgraded this case to UNCERTAIN (QA-026) and lost correct METs on test: v1 only flags it."""
    out = run(ans(evidence=["Built a churn prediction model with gradient boosting"]), req(min_years=2))
    assert out["decision"] == "MET" and out["review_reasons"] == ["duration_not_in_evidence"]


def test_contradicted_but_quote_meets_the_years_is_flagged_not_changed():
    out = run(ans(decision="MISSING", basis="contradicted", evidence=["4 years of experience in SQL reporting"]),
              req(min_years=3))
    assert out["decision"] == "MISSING" and "contradiction_refuted_by_evidence" in out["review_reasons"]


def test_v2_rules_not_kept_do_not_fire():
    """Negation context and weak cues were V2 v2 rules: v1 keeps the model's MET with a verified quote."""
    out = run(ans(evidence=["Did not use Kubernetes in production."]), req(text="Kubernetes", skill_terms=["Kubernetes"]))
    assert out["decision"] == "MET" and out["review_reasons"] == []


def test_quote_too_short_and_duplicates():
    out = run(ans(evidence=["(2", "SQL reporting", "SQL reporting"]))
    assert [e["quote"] for e in out["evidence"]] == ["SQL reporting"]
    assert "evidence_too_short" in out["review_reasons"]


def test_find_span_strips_only_surrounding_whitespace():
    assert find_span(CV_TEXT, "  Hobbies: chess  ") == (CV_TEXT.index("Hobbies"), CV_TEXT.index("Hobbies") + 14)
    assert find_span(CV_TEXT, "hobbies: chess") is None  # case matters: exact substring only


# ------------------------------------------------- /match, mocked server ---

def test_match_sends_schema_lora_1_and_verifies_quotes(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "local")
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        reply = ans(evidence=["4 years of experience in SQL reporting", "invented quote"])
        return httpx.Response(200, json={"choices": [{"message": {"content": reply}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = matcher_mod.match(CV_TEXT, req(), client=client)
    body = seen[0]
    assert body["lora"] == [{"id": 0, "scale": 1.0}] and body["response_format"]["type"] == "json_object"
    assert body["response_format"]["schema"]["required"] == ["decision", "basis", "evidence", "explanation"]
    assert body["temperature"] == 0 and body["max_tokens"] == 384 and CV_TEXT in body["messages"][1]["content"]
    assert out["decision"] == "MET" and [e["quote"] for e in out["evidence"]] == ["4 years of experience in SQL reporting"]
    assert out["review_reasons"] == ["evidence_not_in_cv"] and out["prompt_id"] == "matcher-v1"
    assert len(out["knowledge_refs"]) <= 3


def test_decision_confidence_reads_the_label_token_exactly():
    import math
    tok = lambda t, lp, top: {"token": t, "logprob": lp, "top_logprobs": [{"token": a, "logprob": b} for a, b in top]}  # noqa: E731
    logprobs = {"content": [tok('{"', 0, []), tok("decision", 0, []), tok('":', 0, []), tok(' "', 0, [(' "', 0)]),
                            tok("MET", math.log(0.7), [("MET", math.log(0.7)), ("MISS", math.log(0.2)),
                                                       (" MET", math.log(0.05))]), tok('",', 0, [])]}
    c = matcher_mod.decision_confidence(logprobs)
    assert c["label_prob"] == {"MET": 0.7, "MISSING": 0.2, "UNCERTAIN": None}  # ' MET' is another token, not counted
    assert c["normalized"] == {"MET": round(0.7 / 0.9, 6), "MISSING": round(0.2 / 0.9, 6), "UNCERTAIN": 0.0}
    assert matcher_mod.decision_confidence(None) is None
