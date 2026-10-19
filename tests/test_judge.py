# Adapted from team V2: matcher/tests/test_judge_nli.py (verdict / premise / label-order ideas) (feature/agent-integration @ a5a03ff)
"""NLI Judge (station 6) and the /match confidence rule. Mock NLI except one real-model check (skips without model)."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import api
from services.judge import judge as J
from services.matcher.matcher import apply_confidence_rule

ROOT = Path(__file__).resolve().parents[1]
CV = "Profile\nData analyst with 4 years of experience in SQL reporting.\n- Never used Kubernetes in production.\nHobbies: chess."
REQ = {"req_id": "r1", "text": "Hands-on experience with SQL", "kind": "must", "category": "skill",
       "skill_terms": [], "min_years": None}


def match(decision="MET", basis="supported", quotes=("4 years of experience in SQL reporting",), reasons=()):
    ev = [{"quote": q, "start": CV.find(q), "end": CV.find(q) + len(q)} for q in quotes]
    return {"decision": decision, "basis": basis, "evidence": ev, "review_reasons": list(reasons)}


class FakeJudge(J.NLIJudge):
    """No model: fixed NLI probabilities; records the (premise, hypothesis) pairs it was given."""
    def __init__(self, probs, tau_pass=0.05, tau_fail=0.15):
        self.fixed, self.seen = probs, []
        self.tau_pass, self.tau_fail, self.template, self.model_dir = tau_pass, tau_fail, "v2", "fake"

    def probs(self, pairs, batch_size=16):
        self.seen += pairs
        return [dict(self.fixed) for _ in pairs]


ENT = {"entailment": 0.9, "neutral": 0.08, "contradiction": 0.02}
NEU = {"entailment": 0.03, "neutral": 0.95, "contradiction": 0.02}


def test_met_supported_by_its_quote_passes():
    f = FakeJudge(ENT).judge(CV, REQ, match())
    assert f["verdict"] == "PASS" and f["review_reasons"] == [] and f["premise_kind"] == "quotes"


def test_met_whose_quote_does_not_prove_it_fails():
    f = FakeJudge(NEU).judge(CV, REQ, match())
    assert f["verdict"] == "FAIL" and f["review_reasons"] == ["judge:disagrees"]


def test_missing_not_documented_fails_when_the_cv_entails_the_requirement():
    fj = FakeJudge(ENT)
    f = fj.judge(CV, REQ, match("MISSING", "not_documented", ()))
    assert f["verdict"] == "FAIL" and f["premise_kind"] == "cv" and fj.seen[0][0] == CV  # whole CV as premise
    assert FakeJudge(NEU).judge(CV, REQ, match("MISSING", "not_documented", ()))["verdict"] == "PASS"


def test_uncertain_is_not_applicable_and_no_model_call():
    fj = FakeJudge(ENT)
    f = fj.judge(CV, REQ, match("UNCERTAIN", "ambiguous", ()))
    assert f["verdict"] == "NOT_APPLICABLE" and f["review_reasons"] == [] and fj.seen == []


def test_met_without_a_verified_quote_is_uncertain_without_nli():
    fj = FakeJudge(ENT)
    m = match(quotes=())
    m["evidence"] = [{"quote": "10 years of SQL at Google", "start": 0, "end": 25}]
    f = fj.judge(CV, REQ, m)
    assert f["verdict"] == "UNCERTAIN" and f["review_reasons"] == ["judge:uncertain"] and fj.seen == []
    assert {"evidence_not_in_cv", "missing_evidence"} <= set(f["notes"])


def test_quote_is_read_in_its_cv_line_so_a_negation_is_visible():
    fj = FakeJudge(ENT)
    fj.judge(CV, {**REQ, "text": "Kubernetes in production"}, match(quotes=("Kubernetes in production",)))
    assert fj.seen[0][0] == "Never used Kubernetes in production."  # widened to the line, list marker dropped


def test_premise_is_cv_text_only_never_knowledge():
    fj = FakeJudge(ENT)
    m = match() | {"knowledge_refs": [{"source_id": "esco:x", "title": "SQL is a query language"}]}
    fj.judge(CV, REQ, m)
    assert all(p in CV for p, _ in fj.seen) and "query language" not in json.dumps(fj.seen)


def test_validator_numeric_reasons_are_kept_as_notes():
    f = FakeJudge(ENT).judge(CV, REQ, match(reasons=["duration_not_in_evidence"]))
    assert "validator:duration_not_in_evidence" in f["notes"]


def test_nli_failure_gives_uncertain_not_a_crash():
    class Broken(FakeJudge):
        def probs(self, pairs, batch_size=16):
            raise RuntimeError("CUDA out of memory")
    f = Broken(ENT).judge(CV, REQ, match())
    assert f["verdict"] == "UNCERTAIN" and f["error"].startswith("RuntimeError") and f["review_reasons"] == ["judge:uncertain"]


def test_labels_are_mapped_by_name_not_position():
    assert J.label_index({"0": "contradiction", "1": "neutral", "2": "entailment"}) == \
        {"entailment": 2, "neutral": 1, "contradiction": 0}
    with pytest.raises(ValueError):
        J.label_index({"0": "LABEL_0", "1": "LABEL_1", "2": "LABEL_2"})


def test_hypothesis_templates():
    assert J.hypothesis(REQ, "v2") == "The candidate has hands-on experience with SQL."
    assert J.hypothesis({**REQ, "min_years": 3}, "v1").endswith("(at least 3 years).")


def test_chunks_keep_every_character():
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(100))
    assert "".join(J.chunk_text(text, 300)) == text


# ----------------------------------------------------------------- confidence rule ---

def conf(p_met, p_missing, p_unc):
    return {"normalized": {"MET": p_met, "MISSING": p_missing, "UNCERTAIN": p_unc}}


def out(decision="MISSING", model_decision="MISSING"):
    return {"decision": decision, "basis": "not_documented", "model_decision": model_decision,
            "review_reasons": [], "needs_human_review": False}


def test_low_confidence_becomes_uncertain_and_keeps_the_model_decision():
    o = apply_confidence_rule(out(), conf(0.01, 0.53, 0.46), 0.72)
    assert o["decision"] == "UNCERTAIN" and o["model_decision"] == "MISSING"
    assert o["review_reasons"] == ["match:low_confidence"]


def test_confident_answer_is_unchanged_and_missing_confidence_is_ignored():
    assert apply_confidence_rule(out(), conf(0.0, 0.99, 0.01), 0.72)["decision"] == "MISSING"
    assert apply_confidence_rule(out(), None, 0.72)["review_reasons"] == []


# ----------------------------------------------------------------- /judge endpoint ---

def test_judge_endpoint_passes_the_match_through_and_adds_reasons(monkeypatch):
    monkeypatch.setattr(api, "_JUDGE", FakeJudge(NEU))
    q = "4 years of experience in SQL reporting"
    m = {"req_id": "r1", "decision": "MET", "basis": "supported",
         "evidence": [{"quote": q, "start": CV.find(q), "end": CV.find(q) + len(q)}],
         "explanation": "x", "model_decision": "MET", "evidence_years": None, "review_reasons": ["x_reason"],
         "info_flags": [], "needs_human_review": True, "knowledge_refs": [],
         "model": {"name": "qwen3-4b", "backend": "local", "lora_scale": 1.0, "latency_s": 0.1,
                   "finish_reason": "stop", "max_tokens": 384},
         "confidence": None, "prompt_id": "matcher-v1", "schema": "services/matcher/schema.json",
         "knowledge": "rag.bm25 k=3", "elapsed_s": 1.0}
    r = TestClient(api.app).post("/judge", json={"cv_text": CV, "requirement": REQ, "match": m})
    body = r.json()
    assert r.status_code == 200, body
    assert body["decision"] == "MET" and body["review_reasons"] == ["x_reason", "judge:disagrees"]
    assert body["judge"]["verdict"] == "FAIL"


@pytest.mark.skipif(not (ROOT / "models/DeBERTa-v3-base-mnli-fever-anli/model.safetensors").exists(),
                    reason="model not copied")
def test_real_deberta_on_two_clear_cases():
    j = J.NLIJudge(ROOT / "models/DeBERTa-v3-base-mnli-fever-anli", tau_pass=0.05, tau_fail=0.15, device="cpu")
    assert j.judge(CV, {**REQ, "text": "Experience with SQL"}, match())["verdict"] == "PASS"
    # measured (real-CPU): with template v2 the qualifier "Hands-on" makes the same quote neutral -> FAIL
    assert j.judge(CV, REQ, match())["verdict"] == "FAIL"
    f = j.judge(CV, {**REQ, "text": "experience with Kubernetes in production"},
                match(quotes=("Kubernetes in production",)))
    assert f["verdict"] == "FAIL"  # the line says "Never used Kubernetes in production"
