"""Mock integration tests of the fine-tuned Matcher wiring (Session 2): the REAL OpenAICompatBackend / FallbackBackend /
factory code talks HTTP to fake llama.cpp servers. No model runs here: every answer is scripted (MOCK).

The fake server mimics llama-cpp-python 0.3.16: GET /v1/models lists the loaded aliases, and POST
/v1/chat/completions answers with the default model whatever alias was requested, echoing the requested name."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from matcher import prompt
from matcher.agent import MATCHER_REVIEW, Matcher
from matcher.backends_api import FallbackBackend, OpenAICompatBackend
from matcher.factory import MODELS_CONFIG, build, model_provenance
from matcher.knowledge import NoKnowledge
from matcher.output_adapters import strict_repair
from matcher.pipeline import Pipeline, write_report
from matcher.schemas import MatchReport
from matcher.tests.test_agent_pipeline import CVX, ESCO, GOOD, JOB, Fake

ROOT = Path(__file__).resolve().parents[2]
LORA_SHA = "0b6925b1e3c89b6b266b10bcd30af4c6a0c2dc3a"
LORA_ALIAS, BASE_ALIAS = "Qwen/Qwen3-4B-Instruct-2507+lora", "Qwen/Qwen3-4B-Instruct-2507"


class FakeLlamaServer:
    def __init__(self, aliases, answer):
        self.aliases, self.answer, self.requests = aliases, answer, []
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, obj):
                body = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/v1/models":
                    self._send({"object": "list", "data": [{"id": a, "object": "model"} for a in srv.aliases]})
                else:
                    self.send_error(404)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                srv.requests.append(body)
                content, finish = srv.answer(body)
                self._send({"model": body.get("model"),  # echoed, like llama-cpp-python: NOT proof of the model
                            "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish}],
                            "usage": {"prompt_tokens": 100, "completion_tokens": 20}})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def req_id_of(body):
    """Which requirement a chat request is about (matched on the requirement text in the p1 user message)."""
    user = body["messages"][1]["content"]
    return next(r.req_id for r in JOB.requirements if f": {r.text}\n" in user)


def scripted(answers, finish="stop"):
    return lambda body: (answers[req_id_of(body)] if isinstance(answers[req_id_of(body)], str)
                         else json.dumps({**answers[req_id_of(body)], "explanation": "scripted"}), finish)


DEAD = "http://127.0.0.1:9/v1"  # discard port: connection refused at once


@pytest.fixture
def servers():
    made = []

    def make(aliases, answers, finish="stop"):
        s = FakeLlamaServer(aliases, scripted(answers, finish))
        made.append(s)
        return s
    yield make
    for s in made:
        s.close()


def pipeline(primary_url, fallback_url, knowledge=ESCO, **env):
    e = {"HS_JUDGE": "off", "HS_MATCHER_URL": primary_url, "HS_FALLBACK_URL": fallback_url, "HS_MAX_RETRIES": "0",
         "HS_TIMEOUT": "5", **env}
    return build(e, knowledge=knowledge)


def rows(out):
    return {x["req_id"]: x for x in out["requirements"]}


def test_lora_primary_provenance_per_result_and_report_schema(servers):
    lora, base = servers([LORA_ALIAS], GOOD), servers([BASE_ALIAS], GOOD)
    out = pipeline(lora.url, base.url).run(CVX.model_dump(), JOB.model_dump())
    report = MatchReport.model_validate(out["match_report"])  # frozen contract, extra="forbid"
    for x in out["requirements"]:
        p = x["provenance"]
        assert p["answered_by"] == "primary" and p["role"] == "primary" and p["alias_verified"] is True
        assert p["adapter"]["repo"] == "HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora" and p["adapter"]["sha"] == LORA_SHA
        assert p["base_revision"] == "cdbee75f17c01a7cc42f958dc650907174af0554"
        assert p["weights"]["sha"].startswith("a06e946b") and p["weights"]["quant"] == "Q4_K_M"
        assert p["served_alias"] == LORA_ALIAS and p["prompt_id"] == prompt.PROMPT_VERSION == "p1"
        assert p["knowledge_provider"] == "fixture" and "MOCK" not in p
        assert not any(r.startswith("matcher:") for r in x["review_reasons"])
    assert report.backend["results"]["r1"]["adapter"]["sha"] == LORA_SHA and report.backend["prompt_id"] == "p1"
    assert [r.decision for r in report.results] == ["MET", "MET", "MISSING", "MISSING"]
    assert len(lora.requests) == 4 and not base.requests  # the fallback is not called when the primary answers
    assert all(b["model"] == LORA_ALIAS and b["temperature"] == 0 and b["max_tokens"] == 192 for b in lora.requests)
    assert "adapter HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1" in write_report(out)


def test_json_schema_files_accept_the_report(servers):
    jsonschema = pytest.importorskip("jsonschema")
    lora, base = servers([LORA_ALIAS], GOOD), servers([BASE_ALIAS], GOOD)
    out = pipeline(lora.url, base.url).run(CVX.model_dump(), JOB.model_dump())
    schema = json.loads((ROOT / "matcher/json_schemas/MatchReport.schema.json").read_text())
    jsonschema.validate(out["match_report"], schema)


def test_citations_are_the_ids_shown_in_the_prompt(servers):
    lora, base = servers([LORA_ALIAS], GOOD), servers([BASE_ALIAS], GOOD)
    out = pipeline(lora.url, base.url).run(CVX.model_dump(), JOB.model_dump())
    r2 = rows(out)["r2"]
    sent = next(b for b in lora.requests if req_id_of(b) == "r2")["messages"][1]["content"]
    assert r2["rag_refs"] == [c["source_id"] for c in r2["citations"]] == ["http://data.europa.eu/esco/skill/maven"]
    from matcher.agent import shown_label
    from matcher.schemas import KnowledgeRef
    assert all(f"[{shown_label(KnowledgeRef(**{**c, 'text': ''}))}]" in sent for c in r2["citations"])
    r4 = rows(out)["r4"]  # nothing retrieved: nothing cited, prompt says so
    sent4 = next(b for b in lora.requests if req_id_of(b) == "r4")["messages"][1]["content"]
    assert r4["rag_refs"] == [] and r4["citations"] == [] and "(none retrieved)" in sent4
    assert CVX.text not in json.dumps([c for x in out["requirements"] for c in x["citations"]])


def test_fallback_answer_is_provenanced_and_routed_to_review(servers):
    base = servers([BASE_ALIAS], GOOD)
    out = pipeline(DEAD, base.url).run(CVX.model_dump(), JOB.model_dump())
    report = MatchReport.model_validate(out["match_report"])
    for x in out["requirements"]:
        p = x["provenance"]
        assert p["answered_by"] == "fallback" and p["adapter"] is None and p["served_alias"] == BASE_ALIAS
        assert p["primary_error"] and "matcher:fallback_model_used" in x["review_reasons"] and x["requires_human_review"]
    assert rows(out)["r1"]["final_decision"] == "MET"  # the fallback's decision is kept, only flagged
    assert all(r.needs_human_review and "matcher:fallback_model_used" in r.review_reasons for r in report.results)
    assert report.backend["results"]["r2"]["answered_by"] == "fallback"
    assert "fallback · Qwen/Qwen3-4B-Instruct-2507 · no adapter" in write_report(out)


def test_both_down_never_invents_a_decision_and_report_stays_valid():
    out = pipeline(DEAD, "http://127.0.0.1:7/v1").run(CVX.model_dump(), JOB.model_dump())
    report = MatchReport.model_validate(out["match_report"])
    for x, r in zip(out["requirements"], report.results):
        assert x["final_decision"] == "UNCERTAIN" and x["model_decision"] is None and x["evidence"] == []
        assert x["provenance"]["answered_by"] is None and x["provenance"]["error"]
        assert "matcher:backend_unavailable" in x["review_reasons"] and "matcher:output_unparseable" not in x["review_reasons"]
        assert r.decision == "UNCERTAIN" and r.review_priority == "high" and r.needs_human_review
    assert report.summary.counts == {"MET": 0, "MISSING": 0, "UNCERTAIN": 4}
    assert "no model (all Matcher endpoints failed)" in write_report(out)


MALFORMED = {
    # unparseable -> UNCERTAIN + review, never a decision
    "r1": "I think the candidate is a good fit.",
    # synonym label: strict repair refuses to map it -> UNCERTAIN
    "r2": '{"decision": "YES", "basis": "supported", "evidence": ["Set up Maven builds for twelve Java services."], "explanation": "x"}',
    # cut off by max_tokens inside the explanation: decision kept, routed to review as repaired
    "r3": '{"decision": "MISSING", "basis": "contradicted", "evidence": ["Never used Kubernetes in production; deployments ran on managed VMs."], "explanation": "The CV states the cand',
    # template copied: several labels -> UNCERTAIN
    "r4": '{"decision": "MET|MISSING|UNCERTAIN", "basis": "supported|contradicted", "evidence": [], "explanation": ""}',
}


def test_malformed_json_paths(servers):
    lora, base = servers([LORA_ALIAS], MALFORMED, finish="length"), servers([BASE_ALIAS], GOOD)
    out = pipeline(lora.url, base.url).run(CVX.model_dump(), JOB.model_dump())
    r = rows(out)
    for k in ("r1", "r2", "r4"):
        assert r[k]["final_decision"] == "UNCERTAIN" and r[k]["model_decision"] is None
        assert {"validator:model_output_invalid", "matcher:output_unparseable"} <= set(r[k]["review_reasons"])
    assert r["r3"]["final_decision"] == "MISSING" and r["r3"]["basis"] == "contradicted"
    assert "matcher:output_repaired" in r["r3"]["review_reasons"] and r["r3"]["requires_human_review"]
    assert r["r3"]["provenance"]["repairs"] == ["truncated_output"] and r["r3"]["explanation_model"].endswith("[truncated]")
    assert r["r3"]["matcher_call"]["finish_reason"] == "length"
    assert not base.requests  # a bad answer is not a transport failure: no silent switch to the other model
    MatchReport.model_validate(out["match_report"])


def test_served_alias_mismatch_is_flagged(servers):
    wrong = servers([BASE_ALIAS], GOOD)  # the base model sits on the LoRA port: it would answer the "+lora" alias
    out = pipeline(wrong.url, DEAD).run(CVX.model_dump(), JOB.model_dump())
    for x in out["requirements"]:
        assert x["provenance"]["alias_verified"] is False and x["provenance"]["served_aliases"] == [BASE_ALIAS]
        assert "matcher:served_model_mismatch" in x["review_reasons"] and x["requires_human_review"]


def test_must_have_missing_is_review_never_rejection(servers):
    lora = servers([LORA_ALIAS], GOOD)
    out = pipeline(lora.url, DEAD).run(CVX.model_dump(), JOB.model_dump())
    for x in out["requirements"]:
        if x["final_decision"] == "MISSING" and x["kind"] == "must":
            assert x["requires_human_review"]
    assert "No automatic rejection" in out["summary"]["note"]


def test_scripted_backends_are_labelled_mock():
    out = Pipeline(FallbackBackend(Fake("lora", GOOD), Fake("base", GOOD)), ESCO).run(CVX.model_dump(), JOB.model_dump())
    assert all(x["provenance"]["MOCK"] for x in out["requirements"])
    assert "MOCK backend: not a model result" in write_report(out)
    rep = Matcher(Fake("lora", GOOD), NoKnowledge()).match(CVX, JOB)
    assert all(p["MOCK"] and p["knowledge_provider"] == "none" for p in rep.backend["results"].values())


def test_matcher_report_routes_review_into_the_frozen_contract():
    rep = Matcher(FallbackBackend(Fake("lora", down=True), Fake("base", GOOD)), ESCO).match(CVX, JOB)
    r1 = rep.results[0]
    assert r1.decision == "MET" and r1.needs_human_review and "matcher:fallback_model_used" in r1.review_reasons
    assert r1.review_priority in ("medium", "high") and rep.summary.needs_human_review == 4
    assert set(MATCHER_REVIEW) == {"matcher:backend_unavailable", "matcher:output_unparseable",
                                   "matcher:served_model_mismatch", "matcher:fallback_model_used", "matcher:output_repaired",
                                   "matcher:counterfactual_mixed_models", "bias:reviewer_unavailable"}


class FlakyFake(Fake):
    """Primary that goes down after `n` calls (an outage in the middle of a live counterfactual audit)."""

    def __init__(self, model, answers, n):
        super().__init__(model, answers)
        self.n = n

    def generate(self, task):
        self.down = self.calls >= self.n
        return super().generate(task)


def test_counterfactual_answered_by_another_model_is_flagged():
    one = JOB.model_copy(update={"requirements": JOB.requirements[:1]})
    out = Pipeline(FallbackBackend(FlakyFake("lora", GOOD, n=3), Fake("base", GOOD)), ESCO,
                   live_counterfactual=True).run(CVX.model_dump(), one.model_dump())
    x = out["requirements"][0]
    assert x["provenance"]["answered_by"] == "primary" and "matcher:counterfactual_mixed_models" in x["review_reasons"]
    assert x["final_decision"] == "MET"  # flagged only
    assert "matcher:counterfactual_mixed_models" in out["match_report"]["results"][0]["review_reasons"]
    steady = Pipeline(FallbackBackend(Fake("lora", GOOD), Fake("base", GOOD)), ESCO,
                      live_counterfactual=True).run(CVX.model_dump(), one.model_dump())
    assert "matcher:counterfactual_mixed_models" not in steady["requirements"][0]["review_reasons"]


@pytest.mark.parametrize("raw,decision,repairs", [
    ('```json\n{"decision": "MET", "basis": "supported", "evidence": ["a"], "explanation": "x"}\n```', "MET", ["code_fence"]),
    ("{'decision': 'MISSING', 'basis': 'not_documented', 'evidence': [], 'explanation': 'x'}", "MISSING", ["python_literal"]),
    ('{"Decision": "met", "Basis": "Supported", "evidence": "a", "explanation": "x", "score": 0.9}', "MET",
     ["key_case", "extra_keys_dropped", "label_case", "evidence_coerced"]),
    ('{"decision": "UNCERTAIN", "basis": "ambiguous", "evidence": [], "explanation": "Partly', "UNCERTAIN", ["truncated_output"]),
    ('{"decision": "MATCH", "basis": "supported", "evidence": [], "explanation": ""}', None, ["invalid_decision_label"]),
    ('{"decision": "MET", "basis": "probably", "evidence": [], "explanation": ""}', None, ["invalid_basis_label"]),
    ('{"decision": "MET", "evidence": ["a"], "explanation": "x"}', None, ["decision_or_basis_missing"]),
    ('{"decision": "MET", "basis": "supported", "evidence": ["a", "b', None, ["no_json_object"]),
    ("", None, ["no_json_object"]),
])
def test_strict_repair_never_invents_a_decision(raw, decision, repairs):
    a, r = strict_repair(raw)
    assert (a.decision if a else None) == decision and r == repairs


def test_pinned_config_matches_hub_evidence_and_eval_run():
    cfg = json.loads(MODELS_CONFIG.read_text())
    assert cfg["primary"]["adapter"]["sha"] == LORA_SHA and cfg["fallback"]["adapter"] is None
    ev = ROOT / "benchmark/results/adapter/hs_lora_provenance.json"  # written by the 202-req eval (read-only here)
    if ev.exists():
        e = json.loads(ev.read_text())
        assert (e["repo"], e["sha"]) == (cfg["primary"]["adapter"]["repo"], cfg["primary"]["adapter"]["sha"])
    p, f, _ = model_provenance({"HS_LORA_REPO": "x/other", "HS_LORA_SHA": "abc"})
    assert p["adapter"] == {"repo": "x/other", "sha": "abc"} and f["adapter"] is None


def test_production_default_keeps_rag_and_lora_primary(monkeypatch):
    built = {}
    import matcher.factory as fac
    monkeypatch.setattr(fac, "_knowledge_attr", lambda name: lambda: built.setdefault(name, NoKnowledge()))
    p = build({"HS_JUDGE": "off"})
    assert "GatedKnowledge" in built  # HS_RAG unset -> gated RAG provider (rag.gated.v1), never "none" by default
    b = p.matcher.backend
    assert isinstance(b, FallbackBackend) and isinstance(b.primary, OpenAICompatBackend)
    assert b.primary.base_url.endswith(":8081/v1") and b.primary.model == LORA_ALIAS
    assert b.fallback.base_url.endswith(":8080/v1") and b.fallback.model == BASE_ALIAS
    assert b.info()["primary"]["provenance"]["adapter"]["sha"] == LORA_SHA
    assert b.info()["fallback"]["provenance"]["adapter"] is None


# --- orchestrator findings on the LIVE LoRA val run (2026-10-16): template explanations, false-MET, adapter n/a ---

def test_grounded_explanation_uses_only_validated_content():
    bad = {**GOOD, "r1": {"decision": "MET", "basis": "supported", "evidence": ["10 years of Python at Google"]}}
    out = Pipeline(FallbackBackend(Fake("lora", bad), Fake("base", GOOD)), ESCO).run(CVX.model_dump(), JOB.model_dump())
    r = rows(out)
    for x in out["requirements"]:
        g = x["explanation"]
        assert g.startswith(f'Requirement "{x["requirement_text"]}": {x["final_decision"]}.')
        assert x["explanation_model"] == "scripted"  # the raw model text is kept
        for quoted in g.split('"')[3::2]:  # every quoted string after the requirement is a verified CV quote
            assert quoted in CVX.text
    assert "10 years of Python at Google" not in r["r1"]["explanation"]
    assert "the model said MET but none of its quotes is in the CV" in r["r1"]["explanation"]
    assert "Set up Maven builds" in r["r2"]["explanation"] and "Terminology from: Apache Maven" in r["r2"]["explanation"]
    assert "shows it is not met" in r["r3"]["explanation"]
    assert "absence of evidence, not proof" in r["r4"]["explanation"]
    md = write_report(out)
    assert "- Explanation: Requirement" in md and "- Model text: scripted" in md


def test_met_on_exposure_quote_is_validator_v2_uncertain():
    """Weak-evidence cues live in matcher/validate.py (v2, QA-025); the grounded explanation says why."""
    weak = {**GOOD, "r2": {"decision": "MET", "basis": "supported", "evidence": ["Watched tutorials about Maven in spare time."]}}
    cv = CVX.model_copy(update={"text": CVX.text + "\n- Watched tutorials about Maven in spare time."})
    r2 = rows(Pipeline(FallbackBackend(Fake("lora", weak), Fake("base", GOOD)), ESCO).run(cv.model_dump(), JOB.model_dump()))["r2"]
    assert r2["final_decision"] == "UNCERTAIN" and r2["model_decision"] == "MET" and r2["requires_human_review"]
    assert "validator:weak_evidence_cue" in r2["review_reasons"] and "exposure" in r2["explanation"]


def test_benchmark_style_backend_records_pinned_adapter():
    lora = OpenAICompatBackend(base_url="http://127.0.0.1:8081/v1", model=LORA_ALIAS)  # as benchmark.run builds it
    base = OpenAICompatBackend(base_url="http://127.0.0.1:8080/v1", model=BASE_ALIAS)
    assert (lora.info()["adapter_id"], lora.info()["adapter_revision"]) == ("HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora", LORA_SHA)
    assert base.info()["adapter_id"] is None and base.info()["provenance"]["base_revision"].startswith("cdbee75f")
    hosted = OpenAICompatBackend(base_url="https://x/v1", model=LORA_ALIAS, provider="hosted")
    assert hosted.info()["adapter_id"] is None  # no guess for a hosted endpoint


# --- S4 Bias Auditor wiring (docs/orchestration/requests/s4-bias-auditor-integration.md, S4 code not on this branch) ---

class FakeAuditor:
    """Duck-typed stand-in for bias.auditor.BiasAuditor (same call shape, BiasFinding out)."""

    def __init__(self, variant, reviewer=None, reviewer_error=None):
        self.variant, self.reviewer, self.reviewer_error, self.calls = variant, reviewer, reviewer_error, []

    def info(self):
        return {"variant": self.variant, **({"reviewer": {"model": self.reviewer.backend.model}} if self.reviewer else {})}

    def check_result(self, result, cv_text, requirement_text=None):
        from matcher.bias_audit import check_result
        self.calls.append(requirement_text)
        f = check_result(result, cv_text)
        f.details["auditor"] = self.variant
        if self.reviewer_error:
            f.details["reviewer"] = {"verdict": None, "error": self.reviewer_error}
        return f


class FakeReviewer:
    def __init__(self, backend):
        self.backend = backend


@pytest.fixture
def fake_bias(monkeypatch):
    import sys
    import types
    pkg, aud, rev = types.ModuleType("bias"), types.ModuleType("bias.auditor"), types.ModuleType("bias.reviewer")
    aud.BiasAuditor, rev.LLMReviewer = FakeAuditor, FakeReviewer
    monkeypatch.setitem(sys.modules, "bias", pkg)
    monkeypatch.setitem(sys.modules, "bias.auditor", aud)
    monkeypatch.setitem(sys.modules, "bias.reviewer", rev)


def test_bias_auditor_default_is_rules_v2_without_model_calls():
    p = build({"HS_JUDGE": "off"}, knowledge=ESCO)
    assert p.auditor.variant == "rules_v2" and getattr(p.auditor, "reviewer", None) is None  # no model call by default
    p1 = build({"HS_JUDGE": "off", "HS_BIAS_AUDITOR": "rules_v1"}, knowledge=ESCO)
    assert p1.auditor is None
    out = Pipeline(FallbackBackend(Fake("lora", GOOD), Fake("base", GOOD)), ESCO).run(CVX.model_dump(), JOB.model_dump())
    assert out["match_report"]["backend"]["bias_auditor"] == {"variant": "rules_v1"}


def test_bias_auditor_opt_in_reviewer_on_base_model_only(fake_bias):
    p = build({"HS_JUDGE": "off", "HS_BIAS_AUDITOR": "rules_v2+reviewer"}, knowledge=ESCO)
    assert p.auditor.variant == "rules_v2+reviewer"
    rb = p.auditor.reviewer.backend
    assert rb.base_url.endswith(":8080/v1") and rb.model == BASE_ALIAS and rb.max_tokens == 160
    with pytest.raises(ValueError, match="must not run on the Matcher LoRA"):
        build({"HS_JUDGE": "off", "HS_BIAS_AUDITOR": "rules_v2+reviewer", "HS_BIAS_REVIEWER_MODEL": LORA_ALIAS}, knowledge=ESCO)
    assert build({"HS_JUDGE": "off", "HS_BIAS_AUDITOR": "rules_v2"}, knowledge=ESCO).auditor.reviewer is None


def test_injected_auditor_gets_requirement_text_and_reviewer_failure_is_reviewed():
    aud = FakeAuditor("rules_v2+reviewer", reviewer_error="URLError: refused")
    out = Pipeline(FallbackBackend(Fake("lora", GOOD), Fake("base", GOOD)), ESCO, auditor=aud).run(CVX.model_dump(), JOB.model_dump())
    assert aud.calls == [r.text for r in JOB.requirements]
    assert out["match_report"]["backend"]["bias_auditor"]["variant"] == "rules_v2+reviewer"
    for x in out["requirements"]:
        assert "bias:reviewer_unavailable" in x["review_reasons"] and x["requires_human_review"]
    assert [x["final_decision"] for x in out["requirements"]] == ["MET", "MET", "MISSING", "MISSING"]  # findings only
    assert all("bias:reviewer_unavailable" in r["review_reasons"] for r in out["match_report"]["results"])



# --- S1 requests: HS_RAG gated providers, optional constrained decoding (both opt-in) ---

def test_hs_rag_gated_selects_s1_provider_and_fails_loudly_without_it(monkeypatch):
    import matcher.knowledge as k

    class Gated:
        name, uses_job = "rag.gated.v1+bm25", True

        def lookup(self, req, k=3, job_id=None):
            return []
    if hasattr(k, "GatedKnowledge"):
        monkeypatch.delattr(k, "GatedKnowledge")
    with pytest.raises(ImportError, match="S1"):
        build({"HS_JUDGE": "off", "HS_RAG": "gated"})
    monkeypatch.setattr(k, "GatedKnowledge", Gated, raising=False)
    assert build({"HS_JUDGE": "off", "HS_RAG": "gated"}).matcher.knowledge.name == "rag.gated.v1+bm25"
    with pytest.raises(ValueError, match="HS_RAG"):
        build({"HS_JUDGE": "off", "HS_RAG": "typo"})


def test_json_schema_constraint_is_opt_in_and_recorded(servers):
    lora, base = servers([LORA_ALIAS], GOOD), servers([BASE_ALIAS], GOOD)
    out = pipeline(lora.url, base.url).run(CVX.model_dump(), JOB.model_dump())
    assert "response_format" not in lora.requests[0] and out["requirements"][0]["provenance"]["constrained_decoding"] is None
    p = build({"HS_JUDGE": "off", "HS_JSON_SCHEMA": "fallback", "HS_MATCHER_URL": DEAD, "HS_FALLBACK_URL": base.url,
               "HS_MAX_RETRIES": "0"}, knowledge=ESCO)
    assert p.matcher.backend.primary.response_schema is None
    x = p.run(CVX.model_dump(), JOB.model_dump())["requirements"][0]
    rf = base.requests[-1]["response_format"]
    assert rf["type"] == "json_object" and set(rf["schema"]["required"]) >= {"decision", "basis", "explanation"}
    assert x["provenance"]["constrained_decoding"].startswith("json_schema:ModelAnswer@")
    with pytest.raises(ValueError):
        build({"HS_JUDGE": "off", "HS_JSON_SCHEMA": "yes"}, knowledge=ESCO)
