"""Contract tests pinning the frozen v1 interfaces (docs/orchestration/ORCHESTRATION.md §3). MOCK backends only.

A failure here means a frozen interface changed: either the change goes through the orchestrator (and this file is
updated with the new version), or it is a regression.
"""
import copy
import inspect
import json
import tempfile
from pathlib import Path

import pytest
from _qa_support import CVX, GOOD, JOB, Scripted, ans, check, defect, provenance_problems, ref

from matcher import knowledge
from matcher.agent import Matcher
from matcher.backends_api import FallbackBackend
from matcher.bias_audit import counterfactual
from matcher.factory import build
from matcher.pipeline import Pipeline
from matcher.schemas import SCHEMA_VERSION, KnowledgeRef, MatchReport, ModelAnswer, RequirementResult, export_json_schemas
from matcher.tests.test_pipeline import FakeJudge

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "matcher" / "json_schemas"


# ---- 1. knowledge provider ---------------------------------------------------------------------------------------
class SpyKnowledge:
    """Records every lookup call; returns one fixed KnowledgeRef."""
    name = "spy"
    uses_job = True

    def __init__(self, refs=None):
        self.calls, self.refs = [], refs if refs is not None else [ref("esco/maven", "Apache Maven", ["Maven"])]

    def lookup(self, req, k=3, job_id=None):
        self.calls.append({"req": req, "k": k, "job_id": job_id})
        return list(self.refs)


def _cv_fragments(text):
    return [ln.strip() for ln in text.splitlines() if len(ln.strip()) > 12]


PROVIDERS = [knowledge.FixtureKnowledge, knowledge.RagKnowledge, knowledge.NoKnowledge, knowledge.QdrantKnowledge]


@pytest.mark.parametrize("cls", [pytest.param(c, marks=defect("QA-001", "S1") if c is not knowledge.QdrantKnowledge else ())
                                 for c in PROVIDERS], ids=lambda c: c.__name__)
def test_lookup_signature_is_frozen_v1(cls):
    """lookup(req: Requirement, k: int = 3, job_id: str | None = None) -> list[KnowledgeRef]"""
    params = list(inspect.signature(cls.lookup).parameters.values())
    assert [p.name for p in params] == ["self", "req", "k", "job_id"]
    assert params[2].default == 3 and params[3].default is None


@pytest.mark.parametrize("live_cf", [False, True])
def test_lookup_never_receives_cv_text(live_cf):
    spy = SpyKnowledge()
    Pipeline(Scripted(), spy, live_counterfactual=live_cf).run(CVX.model_dump(), JOB.model_dump())
    Matcher(Scripted(), spy).match(CVX, JOB)
    assert spy.calls, "knowledge provider was never called"
    frags = _cv_fragments(CVX.text)
    for call in spy.calls:
        assert type(call["req"]).__name__ == "Requirement" and isinstance(call["k"], int)
        assert call["job_id"] in (None, JOB.job_id)
        blob = json.dumps({**call, "req": call["req"].model_dump()})
        assert not [f for f in frags if f in blob], "CV text reached the knowledge provider"


def test_lookup_may_abstain_with_empty_list():
    out = Pipeline(Scripted(), SpyKnowledge(refs=[])).run(CVX.model_dump(), JOB.model_dump())
    assert all(r["rag_refs"] == [] and r["citations"] == [] for r in out["requirements"])


def test_fixture_provider_returns_valid_knowledge_refs():
    fk = knowledge.FixtureKnowledge([{"source_id": "esco/maven", "title": "Apache Maven", "aliases": ["Maven"], "text": "t"}])
    refs = fk.lookup(JOB.requirements[1])
    assert refs and all(isinstance(r, KnowledgeRef) and r.source_type and r.source_id and r.retrieval for r in refs)


# ---- 3. matcher output schemas -----------------------------------------------------------------------------------
def test_json_schema_files_match_pydantic_models():
    with tempfile.TemporaryDirectory() as d:
        export_json_schemas(d)
        for f in sorted(Path(d).iterdir()):
            assert (SCHEMAS / f.name).read_text() == f.read_text(), f"{f.name} drifted from matcher/schemas.py"


def _props(schema, name=None):
    s = schema["$defs"][name] if name else schema
    return set(s["properties"]), set(s.get("required", [])), s.get("additionalProperties")


def test_frozen_v1_field_sets():
    assert SCHEMA_VERSION == "1.0.0"
    ma = json.loads((SCHEMAS / "ModelAnswer.schema.json").read_text())
    assert _props(ma) == ({"decision", "basis", "evidence", "explanation"}, {"decision", "basis", "explanation"}, False)
    assert ma["properties"]["decision"]["enum"] == ["MET", "MISSING", "UNCERTAIN"]
    assert ma["properties"]["basis"]["enum"] == ["supported", "contradicted", "not_documented", "ambiguous"]
    assert ma["properties"]["evidence"]["maxItems"] == 3
    kr = json.loads((SCHEMAS / "KnowledgeRef.schema.json").read_text())
    props, required, extra = _props(kr)
    assert {"source_type", "source_id", "retrieval"} <= required and extra is False
    assert props == {"source_type", "source_id", "title", "text", "url", "aliases", "relevance_score", "retrieval"}
    mr = json.loads((SCHEMAS / "MatchReport.schema.json").read_text())
    assert _props(mr)[0] == {"schema_version", "cv_id", "job_id", "backend", "results", "summary"}
    rr_props, rr_req, rr_extra = _props(mr, "RequirementResult")
    assert rr_props == set(RequirementResult.model_fields) and rr_extra is False
    assert {"decision", "basis", "evidence", "evidence_spans", "rag_refs", "model_decision", "needs_human_review",
            "review_reasons"} <= rr_req


def test_match_report_roundtrip_and_spans_are_verbatim():
    rep = Matcher(Scripted(), SpyKnowledge()).match(CVX, JOB)
    again = MatchReport.model_validate_json(rep.model_dump_json())
    assert again == rep
    for r in rep.results:
        assert len(r.evidence) == len(r.evidence_spans)
        assert all(CVX.text[a:b] == q for q, (a, b) in zip(r.evidence, r.evidence_spans))
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.validate(json.loads(rep.model_dump_json()), json.loads((SCHEMAS / "MatchReport.schema.json").read_text()))


def test_model_answer_rejects_extra_and_invalid_fields():
    with pytest.raises(Exception):
        ModelAnswer.model_validate({"decision": "MET", "basis": "supported", "evidence": [], "explanation": "", "x": 1})
    with pytest.raises(Exception):
        ModelAnswer.model_validate({"decision": "NOT_MET", "basis": "supported", "evidence": [], "explanation": ""})


def test_missing_evidence_is_never_met_and_never_contradicted():
    r = JOB.requirements[2]
    met = check("MET", "supported", [], CVX, r)
    assert met.decision == "UNCERTAIN" and met.needs_human_review and met.model_decision == "MET"
    contra = check("MISSING", "contradicted", [], CVX, r)
    assert contra.basis == "not_documented" and contra.needs_human_review  # must-have


# ---- 4. provenance -----------------------------------------------------------------------------------------------
def test_provenance_records_prompt_and_knowledge():
    rep = Matcher(Scripted(), SpyKnowledge()).match(CVX, JOB)
    assert rep.backend["knowledge"] == "spy"
    out = Pipeline(Scripted(), SpyKnowledge()).run(CVX.model_dump(), JOB.model_dump())
    assert out["knowledge"] == "spy" and all("matcher_call" in r for r in out["requirements"])


@defect("QA-014", "S2")
def test_production_provenance_is_complete(monkeypatch):
    """MatchReport.backend of the factory-built Matcher (LoRA primary + base fallback) names model, base revision,
    adapter repo + sha, knowledge provider + version and prompt id. The HTTP call is stubbed (MOCK)."""
    from matcher.backends_api import OpenAICompatBackend

    canned = {"choices": [{"message": {"content": ans(*GOOD["r1"])}}], "usage": {}}
    monkeypatch.setattr(OpenAICompatBackend, "_post", lambda self, payload: canned)
    p = build({"HS_JUDGE": "off"}, knowledge=knowledge.NoKnowledge())
    rep = Matcher(p.matcher.backend, p.matcher.knowledge).match(CVX, JOB.model_copy(update={"requirements": JOB.requirements[:1]}))
    assert provenance_problems(rep.backend) == []


@defect("QA-013", "S2")
def test_match_report_routes_fallback_results_to_review():
    rep = Matcher(FallbackBackend(Scripted("lora", mode="down"), Scripted("base")), SpyKnowledge()).match(CVX, JOB)
    assert all(r.needs_human_review for r in rep.results)
    assert all(any("fallback" in x for x in r.review_reasons) for r in rep.results)


def test_pipeline_routes_fallback_results_to_review():
    out = Pipeline(FallbackBackend(Scripted("lora", mode="down"), Scripted("base")), SpyKnowledge()).run(
        CVX.model_dump(), JOB.model_dump())
    for r in out["requirements"]:
        assert r["matcher_call"]["used"] == "fallback" and r["requires_human_review"]
        assert "matcher:fallback_model_used" in r["review_reasons"]


# ---- 5/6. Bias Auditor and Judge add findings only ---------------------------------------------------------------
def _decisions(out):
    return [(r["req_id"], r["final_decision"], r["basis"], r["evidence"], r["model_decision"]) for r in out["requirements"]]


def test_judge_and_bias_auditor_never_overwrite_a_decision():
    def biased(t):  # nationality-sensitive Matcher
        return ans("MISSING", "not_documented") if "Tunisian" in t.cv.text else ans(*GOOD[t.req.req_id])
    plain = Pipeline(Scripted(fn=biased), SpyKnowledge()).run(CVX.model_dump(), JOB.model_dump())
    always_fail = FakeJudge(lambda p, h: {"entailment": 0.01, "neutral": 0.01, "contradiction": 0.98})
    audited = Pipeline(Scripted(fn=biased), SpyKnowledge(), judge=always_fail, live_counterfactual=True).run(
        CVX.model_dump(), JOB.model_dump())
    assert _decisions(plain) == _decisions(audited)
    assert any(r["bias_audit"]["counterfactual_flip"] for r in audited["requirements"])
    assert any(r["judge"]["judge_verdict"] == "FAIL" for r in audited["requirements"])
    assert all(r["requires_human_review"] for r in audited["requirements"] if r["bias_audit"]["counterfactual_flip"])


def test_judge_and_auditor_do_not_mutate_results_or_cv():
    m = Matcher(Scripted(), SpyKnowledge())
    res = [m.match_requirement(CVX, r)[0] for r in JOB.requirements]
    before, cv_before = [copy.deepcopy(r.model_dump()) for r in res], CVX.model_dump()
    FakeJudge(lambda p, h: {"entailment": 0.0, "neutral": 0.0, "contradiction": 1.0}).judge_many(
        [(r, CVX, q) for r, q in zip(res, JOB.requirements)])
    counterfactual(lambda c, q: m.match_requirement(c, q)[0], CVX, JOB.requirements[0])
    assert [r.model_dump() for r in res] == before and CVX.model_dump() == cv_before
