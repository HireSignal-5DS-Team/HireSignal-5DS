"""Tests for the approved order Matcher -> Validator -> Bias Auditor -> NLI Judge -> Aggregator -> Report Writer.
No model weights needed: the Judge mapping is tested with fixed NLI probabilities, the Matcher with mocks."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from matcher import CV, Job, Requirement
from matcher.backends import LexicalBaseline, MockBackend, Task
from matcher.backends_api import OpenAICompatBackend
from matcher.bias_audit import ATTRIBUTES, check_result, counterfactual, variant
from matcher.judge import NLIJudge, hypothesis
from matcher.knowledge import FixtureKnowledge, NoKnowledge
from matcher.pipeline import Pipeline, aggregate, write_report
from matcher.validate import parse_model_output, validate

CV_TEXT = "Profile\nBackend developer.\n- 5 years of professional Python experience.\n- Has not worked with Kubernetes so far."
CVX = CV(cv_id="c1", text=CV_TEXT)
PY = Requirement(req_id="r1", text="At least 3 years of Python", category="experience", skill_terms=["Python"], min_years=3)
K8S = Requirement(req_id="r2", text="Proficiency in Kubernetes", skill_terms=["Kubernetes"])
JOB = Job(job_id="j1", title="Backend", requirements=[PY, K8S])


def ans(decision, basis, evidence=(), expl="x"):
    return json.dumps({"decision": decision, "basis": basis, "evidence": list(evidence), "explanation": expl})


def validated(raw, req, cv=CVX):
    return validate(parse_model_output(raw), cv, req, [])


class FakeJudge(NLIJudge):
    """NLIJudge with fixed probabilities instead of a DeBERTa forward pass (mapping logic only)."""

    def __init__(self, probs, tau=0.5):
        self._p, self.tau_pass, self.tau_fail, self.name = probs, tau, tau, "fake-nli"

    def probs(self, pairs, batch_size=16):
        return [self._p(p, h) for p, h in pairs]


E = {"entailment": 0.9, "neutral": 0.05, "contradiction": 0.05}
C = {"entailment": 0.05, "neutral": 0.05, "contradiction": 0.9}
N = {"entailment": 0.1, "neutral": 0.8, "contradiction": 0.1}


# ---- Judge mapping -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("decision,basis,ev,probs,verdict", [
    ("MET", "supported", ["5 years of professional Python experience."], E, "PASS"),
    ("MET", "supported", ["5 years of professional Python experience."], C, "FAIL"),
    ("MET", "supported", ["5 years of professional Python experience."], N, "FAIL"),   # quote does not establish it
    ("MISSING", "contradicted", ["Has not worked with Kubernetes so far."], C, "PASS"),
    ("MISSING", "contradicted", ["Has not worked with Kubernetes so far."], E, "FAIL"),
    ("MISSING", "not_documented", [], N, "PASS"),   # absence is not disproof: neutral supports not_documented
    ("MISSING", "not_documented", [], C, "PASS"),
    ("MISSING", "not_documented", [], E, "FAIL"),   # the CV does show it
])
def test_judge_mapping(decision, basis, ev, probs, verdict):
    req = PY if "Python" in "".join(ev) or decision == "MISSING" and basis == "not_documented" else K8S
    res = validated(ans(decision, basis, ev), req)
    assert res.decision == decision  # the validator kept it
    f = FakeJudge(lambda p, h: probs).judge_many([(res, CVX, req)])[0]
    assert f.judge_verdict == verdict and f.judge_disagrees == (verdict == "FAIL")
    assert f.requires_human_review == (verdict != "PASS")


def test_judge_not_applicable_on_uncertain_and_hypothesis():
    res = validated(ans("UNCERTAIN", "ambiguous"), K8S)
    f = FakeJudge(lambda p, h: E).judge_many([(res, CVX, K8S)])[0]
    assert f.judge_verdict == "NOT_APPLICABLE" and f.requires_human_review
    assert hypothesis(PY) == "The candidate meets this job requirement: At least 3 years of Python (at least 3 years)."


def test_judge_never_overwrites_decision():
    res = validated(ans("MET", "supported", ["5 years of professional Python experience."]), PY)
    row = aggregate(res, check_result(res, CVX.text), FakeJudge(lambda p, h: C).judge_many([(res, CVX, PY)])[0])
    assert row["final_decision"] == "MET" and row["judge"]["judge_verdict"] == "FAIL"
    assert row["requires_human_review"] and "judge:disagrees" in row["review_reasons"]


# ---- Bias Auditor --------------------------------------------------------------------------------------------
def test_variants_keep_job_relevant_text_and_quotes_valid():
    for attr in ATTRIBUTES:
        a, b = variant(CV_TEXT, attr, "A"), variant(CV_TEXT, attr, "B")
        assert a != b and a.endswith(CV_TEXT) and b.endswith(CV_TEXT)
        assert "5 years of professional Python experience." in a


def test_counterfactual_detects_known_bias_and_passes_unbiased():
    def run(backend):
        return lambda cv, req: validate(parse_model_output(backend.generate(Task(cv, req, []))), cv, req, [])
    biased = MockBackend(lambda t: ans("MISSING", "not_documented") if "Tunisian" in t.cv.text
                         else ans("MET", "supported", ["5 years of professional Python experience."]), label="biased")
    f = counterfactual(run(biased), CVX, PY)
    assert f.audit_status == "FLAGGED" and f.affected_attribute == "nationality_signal" and f.requires_human_review
    f2 = counterfactual(run(LexicalBaseline()), CVX, PY)  # ignores protected attributes
    assert f2.audit_status == "PASS" and f2.counterfactual_flip is False


def test_leakage_and_demographic_evidence():
    cv = CV(cv_id="c2", text=variant(CV_TEXT, "age_signal", "B"))
    res = validate(parse_model_output(ans("MISSING", "contradicted", ["Year of birth: 1966"], "Born in 1966, too old.")), cv, PY, [])
    f = check_result(res, cv.text)
    assert f.audit_status == "FLAGGED" and f.demographic_evidence and {"born", "old"} <= set(f.leakage_terms)
    clean = validated(ans("MET", "supported", ["5 years of professional Python experience."], "Python years shown."), PY)
    assert check_result(clean, CV_TEXT).audit_status == "PASS"


# ---- Pipeline / aggregation / report -------------------------------------------------------------------------
def test_pipeline_order_routing_and_report():
    def fn(t):
        if t.req.req_id == "r1":
            return ans("MET", "supported", ["5 years of professional Python experience."])
        return ans("MET", "supported", ["Has not worked with Kubernetes so far."])  # negation error
    judge = FakeJudge(lambda p, h: C if "not worked" in p else E)
    out = Pipeline(MockBackend(fn, "scripted"), FixtureKnowledge([]), judge=judge).run(CVX.model_dump(), JOB.model_dump())
    r1, r2 = out["requirements"]
    assert r1["final_decision"] == "MET" and not r1["requires_human_review"] and r1["judge"]["judge_verdict"] == "PASS"
    assert r2["final_decision"] == "MET" and r2["requires_human_review"] and r2["judge"]["judge_verdict"] == "FAIL"
    assert out["summary"]["requires_human_review"] == 1 and "No automatic rejection" in out["summary"]["note"]
    md = write_report(out)
    assert "**REQUIRED** — " in md and "judge:disagrees" in md and "Has not worked with Kubernetes so far." in md


def test_fabricated_quote_and_invalid_json_route_to_review():
    out = Pipeline(MockBackend(lambda t: "not json" if t.req.req_id == "r1" else ans("MET", "supported", ["10 years of Kubernetes"]), "bad"),
                   NoKnowledge()).run(CVX.model_dump(), JOB.model_dump())
    r1, r2 = out["requirements"]
    assert r1["final_decision"] == "UNCERTAIN" and "validator:model_output_invalid" in r1["review_reasons"]
    assert r2["final_decision"] == "UNCERTAIN" and r2["model_decision"] == "MET"
    assert "validator:evidence_not_in_cv" in r2["review_reasons"] and r2["evidence"] == []


# ---- OpenAI-compatible backend: success, timeout, unavailable --------------------------------------------------
class _H(BaseHTTPRequestHandler):
    mode = "ok"

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        if _H.mode == "slow":
            import time
            time.sleep(2)
        if _H.mode == "404":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps({"choices": [{"message": {"content": ans("UNCERTAIN", "ambiguous")}}],
                           "usage": {"prompt_tokens": 11, "completion_tokens": 7}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def server():
    s = ThreadingHTTPServer(("127.0.0.1", 0), _H)  # QA-024: a slow request must not block the next one
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}/v1"
    s.shutdown()


def test_api_backend_success_timeout_and_unavailable(server, monkeypatch):
    monkeypatch.setenv("HS_LLM_API_KEY", "sk-test-not-logged")
    b = OpenAICompatBackend(base_url=server, model="m", timeout=1, max_retries=1)
    _H.mode = "ok"
    assert parse_model_output(b.generate(Task(CVX, PY, []))).decision == "UNCERTAIN"
    assert b.last_call["prompt_tokens"] == 11 and b.last_call["error"] is None
    assert "sk-test" not in json.dumps(b.info())  # secret never exposed
    _H.mode = "slow"
    assert b.generate(Task(CVX, PY, [])) == "" and "timed out" in b.last_call["error"].lower() and b.last_call["attempts"] == 2
    _H.mode = "404"
    assert b.generate(Task(CVX, PY, [])) == "" and b.last_call["attempts"] == 1  # not retried
    down = OpenAICompatBackend(base_url="http://127.0.0.1:9/v1", model="m", timeout=1, max_retries=0)
    assert down.generate(Task(CVX, PY, [])) == "" and down.last_call["error"]
    # the empty answer becomes an invalid-output UNCERTAIN, never a decision
    assert validated("", PY).review_reasons == ["model_output_invalid", "uncertain_decision"]


def test_missing_rag_results_still_validates():
    out = Pipeline(LexicalBaseline(), NoKnowledge()).run(CVX.model_dump(), JOB.model_dump())
    assert [r["rag_refs"] for r in out["requirements"]] == [[], []]
