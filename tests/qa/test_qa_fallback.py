"""Fallback and failure handling: LoRA down, both down, timeouts, malformed model output, malformed server responses.
Rule under test: a failure gives UNCERTAIN + human review, never an invented decision. MOCK servers (a local HTTP
stub that speaks the OpenAI chat-completions shape), no model.
"""
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from _qa_support import CVX, JOB, Scripted, ans

from matcher.backends_api import FallbackBackend, OpenAICompatBackend
from matcher.pipeline import Pipeline
from matcher.validate import parse_model_output


class _None:
    name = "none"

    def lookup(self, req, k=3, job_id=None):
        return []


def run(backend, judge=None):
    return Pipeline(backend, _None(), judge=judge).run(CVX.model_dump(), JOB.model_dump())


def assert_never_invented(row):
    assert row["final_decision"] == "UNCERTAIN" and row["evidence"] == [] and row["requires_human_review"]


# ---- scripted backends -------------------------------------------------------------------------------------------
def test_lora_down_uses_fallback_and_routes_to_review():
    lora, base = Scripted("lora", mode="down"), Scripted("base")
    out = run(FallbackBackend(lora, base))
    assert lora.calls == base.calls == len(JOB.requirements)
    for r in out["requirements"]:
        assert r["matcher_call"]["used"] == "fallback" and r["matcher_call"]["model"] == "base"
        assert r["matcher_call"]["primary_error"] and "matcher:fallback_model_used" in r["review_reasons"]


def test_primary_healthy_never_calls_fallback():
    base = Scripted("base")
    out = run(FallbackBackend(Scripted("lora"), base))
    assert base.calls == 0 and all(r["matcher_call"]["used"] == "primary" for r in out["requirements"])


def test_both_down_is_uncertain_never_invented():
    out = run(FallbackBackend(Scripted("lora", mode="down"), Scripted("base", mode="down")))
    for r in out["requirements"]:
        assert_never_invented(r)
        assert r["model_decision"] is None and "matcher:backend_unavailable" in r["review_reasons"]


@pytest.mark.parametrize("raw", [
    "", "I think the candidate is a good fit.", '{"decision": "MET", "basis": "supported", "evidence": ["Python"]',  # truncated
    '{"decision": "PROBABLY", "basis": "supported", "evidence": [], "explanation": "x"}',
    '{"decision": "MET", "basis": "supported", "evidence": ["a", "b", "c", "d"], "explanation": "x"}',  # > 3 quotes
    '{"decision": "MET", "basis": "supported", "evidence": [], "explanation": "x", "confidence": 0.99}',  # extra key
    "<think>The CV shows Python.</think>", '["MET"]', "null",
])
def test_malformed_model_output_is_uncertain_and_reviewed(raw):
    out = run(Scripted(fn=lambda t: raw))
    for r in out["requirements"]:
        assert_never_invented(r)
        assert "validator:model_output_invalid" in r["review_reasons"] or r["model_decision"] is not None


def test_malformed_output_does_not_trigger_fallback():
    """Fallback is for transport failure only; a bad answer from the LoRA is reviewed, not silently replaced."""
    base = Scripted("base")
    run(FallbackBackend(Scripted("lora", fn=lambda t: "not json"), base))
    assert base.calls == 0


def test_json_wrapped_in_prose_or_fences_is_parsed():
    a = parse_model_output('Sure!\n```json\n' + ans("MISSING", "not_documented") + '\n```')
    assert a and a.decision == "MISSING"
    assert parse_model_output("<think>{\"decision\": \"MET\"}</think>" + ans("UNCERTAIN", "ambiguous")).decision == "UNCERTAIN"


def test_backend_exception_does_not_crash_the_pipeline():
    out = run(FallbackBackend(Scripted("lora", mode="raise"), Scripted("base")))
    assert all(r["matcher_call"]["used"] == "fallback" for r in out["requirements"])


# ---- real OpenAICompatBackend against a local stub server --------------------------------------------------------
class _Stub(BaseHTTPRequestHandler):
    body = b"{}"
    delay = 0.0

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        if _Stub.delay:
            import time
            time.sleep(_Stub.delay)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(_Stub.body)

    def log_message(self, *a):
        pass


@pytest.fixture
def stub():
    s = HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    _Stub.delay, _Stub.body = 0.0, b"{}"
    yield f"http://127.0.0.1:{s.server_port}/v1"
    s.shutdown()


def _api(url, timeout=1.0):
    return OpenAICompatBackend(base_url=url, model="stub", timeout=timeout, max_retries=0)


def test_primary_timeout_falls_back(stub):
    _Stub.delay = 1.5
    out = run(FallbackBackend(_api(stub, timeout=0.3), Scripted("base")))
    assert all(r["matcher_call"]["used"] == "fallback" and "timed out" in r["matcher_call"]["primary_error"].lower()
               for r in out["requirements"])


@pytest.mark.parametrize("body", [b"not json at all", b'{"choices": []}', b'{"error": "model not loaded"}',
                                  b'{"choices": [{"message": {"content": null}}]}'])
def test_handled_malformed_server_responses_are_uncertain(stub, body):
    _Stub.body = body
    out = run(_api(stub))
    for r in out["requirements"]:
        assert_never_invented(r)


@pytest.mark.parametrize("body", [b"[]", b'{"choices": null}', b'{"choices": [{"message": {"content": ["MET"]}}]}'])
def test_unhandled_malformed_server_responses_do_not_crash(stub, body):
    _Stub.body = body
    out = run(FallbackBackend(_api(stub), Scripted("base")))
    assert all(r["matcher_call"]["used"] == "fallback" for r in out["requirements"])


def test_fallback_answer_is_still_validated(stub):
    """The fallback model's fabricated quote is rejected exactly like the primary's."""
    fab = Scripted("base", fn=lambda t: ans("MET", "supported", ["Kubernetes administrator for 8 years."]))
    out = run(FallbackBackend(Scripted("lora", mode="down"), fab))
    for r in out["requirements"]:
        assert r["final_decision"] == "UNCERTAIN" and "validator:evidence_not_in_cv" in r["review_reasons"]
