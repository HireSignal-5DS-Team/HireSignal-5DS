"""Integration tests of the full agent flow on a realistic (fictional, anonymised) CV and job:
Matcher (LoRA primary + base fallback) -> Validator -> Bias Auditor -> NLI Judge -> Aggregator -> Report.
Models are scripted fakes here; live model tests run separately (scripts/run_pipeline.py)."""
import json
from pathlib import Path

import pytest

from matcher import CV, Job
from matcher.backends_api import FallbackBackend
from matcher.factory import FINETUNED_JUDGE, PRETRAINED_JUDGE, build, judge_config
from matcher.knowledge import FixtureKnowledge, QdrantKnowledge
from matcher.pipeline import Pipeline, write_report
from matcher.tests.test_pipeline import FakeJudge

CV_TEXT = """Candidate profile (anonymised)

Summary
Backend engineer focused on payment systems.

Experience
- Senior Python developer at a fintech scale-up (2019 - present).
- Set up Maven builds for twelve Java services.
- Never used Kubernetes in production; deployments ran on managed VMs.
- Mentored three junior developers.

Education
- MSc in Computer Science (2018)."""
CVX = CV(cv_id="cv-demo-1", text=CV_TEXT)
JOB = Job(job_id="job-demo-1", title="Backend engineer", requirements=[
    {"req_id": "r1", "text": "At least 5 years of Python", "category": "experience", "skill_terms": ["Python"], "min_years": 5},
    {"req_id": "r2", "text": "Experience with Apache Maven", "skill_terms": ["Apache Maven"]},
    {"req_id": "r3", "text": "Hands-on Kubernetes experience", "skill_terms": ["Kubernetes"]},
    {"req_id": "r4", "text": "Experience with Apache Kafka", "skill_terms": ["Apache Kafka"]},
])
ESCO = FixtureKnowledge([{"source_id": "http://data.europa.eu/esco/skill/maven", "source_type": "esco", "title": "Apache Maven",
                          "aliases": ["Maven"], "text": "Apache Maven. Also known as: Maven. Build automation tool.",
                          "url": "http://data.europa.eu/esco/skill/maven"}])
GOOD = {  # what a correct Matcher answers
    "r1": {"decision": "MET", "basis": "supported", "evidence": ["Senior Python developer at a fintech scale-up (2019 - present)."]},
    "r2": {"decision": "MET", "basis": "supported", "evidence": ["Set up Maven builds for twelve Java services."]},
    "r3": {"decision": "MISSING", "basis": "contradicted", "evidence": ["Never used Kubernetes in production; deployments ran on managed VMs."]},
    "r4": {"decision": "MISSING", "basis": "not_documented", "evidence": []},
}


class Fake:
    """OpenAICompatBackend stand-in: scripted answers, optional outage, records last_call like the real backend."""

    def __init__(self, model, answers=None, down=False, fn=None):
        self.model, self.answers, self.down, self.fn, self.calls = model, answers or {}, down, fn, 0
        self.last_call = {}

    def info(self):
        return {"backend": "fake", "model_id": self.model, "is_model": False}

    def generate(self, task):
        self.calls += 1
        if self.down:
            self.last_call = {"error": "URLError: connection refused", "latency_s": 0.0}
            return ""
        self.last_call = {"error": None, "latency_s": 0.01}
        a = self.fn(task) if self.fn else self.answers[task.req.req_id]
        return json.dumps({**a, "explanation": "scripted"})


def judge_for(cv_text):
    """NLI stand-in: a negated quote contradicts the requirement; the CV entails what it states; else neutral."""
    def probs(premise, hyp):
        if "Never used" in premise and "Kubernetes" in hyp and len(premise) < 200:
            return {"entailment": 0.02, "neutral": 0.03, "contradiction": 0.95}
        if len(premise) > 200:  # whole CV for not_documented
            return {"entailment": 0.9 if "Kafka" not in hyp else 0.05, "neutral": 0.08, "contradiction": 0.02}
        return {"entailment": 0.93, "neutral": 0.05, "contradiction": 0.02}
    return FakeJudge(probs)


def run(backend, **kw):
    return Pipeline(backend, ESCO, judge=judge_for(CV_TEXT), **kw).run(CVX.model_dump(), JOB.model_dump())


def test_correct_matcher_full_flow_with_citations():
    out = run(FallbackBackend(Fake("lora", GOOD), Fake("base", GOOD)))
    r = {x["req_id"]: x for x in out["requirements"]}
    assert [r[k]["final_decision"] for k in ("r1", "r2", "r3", "r4")] == ["MET", "MET", "MISSING", "MISSING"]
    assert r["r1"]["judge"]["judge_verdict"] == "PASS" and r["r1"]["matcher_call"]["used"] == "primary"
    # related skill: CV says "Maven", requirement says "Apache Maven"; ESCO alias explains it and is cited
    assert r["r2"]["citations"][0]["title"] == "Apache Maven" and r["r2"]["evidence"] == GOOD["r2"]["evidence"]
    assert "semantic_inference_no_term_in_quote" not in r["r2"]["validator"]["reasons"]
    # contradiction is a supported MISSING; missing evidence is not proof of absence -> review, never rejection
    assert r["r3"]["basis"] == "contradicted" and r["r3"]["judge"]["judge_verdict"] == "PASS"
    assert r["r4"]["basis"] == "not_documented" and r["r4"]["requires_human_review"]
    assert "No automatic rejection" in out["summary"]["note"]
    md = write_report(out)
    assert "Set up Maven builds" in md and "**REQUIRED**" in md


def test_negation_error_is_flagged_not_overwritten():
    bad = {**GOOD, "r3": {"decision": "MET", "basis": "supported", "evidence": ["Never used Kubernetes in production; deployments ran on managed VMs."]}}
    r3 = {x["req_id"]: x for x in run(FallbackBackend(Fake("lora", bad), Fake("base", GOOD)))["requirements"]}["r3"]
    assert r3["final_decision"] == "MET" and r3["judge"]["judge_verdict"] == "FAIL"  # decision preserved, flagged
    assert "judge:disagrees" in r3["review_reasons"] and r3["requires_human_review"]


def test_fabricated_evidence_and_wrong_years():
    bad = {**GOOD, "r1": {"decision": "MET", "basis": "supported", "evidence": ["10 years of Python at Google"]}}
    r1 = {x["req_id"]: x for x in run(FallbackBackend(Fake("lora", bad), Fake("base", GOOD)))["requirements"]}["r1"]
    assert r1["final_decision"] == "UNCERTAIN" and r1["model_decision"] == "MET" and r1["evidence"] == []
    assert {"validator:evidence_not_in_cv", "validator:met_without_verified_evidence"} <= set(r1["review_reasons"])


def test_unfair_matcher_caught_by_live_counterfactual():
    def biased(task):  # rejects the same CV when only the nationality line changes
        if "Nationality: Tunisian" in task.cv.text:
            return {"decision": "MISSING", "basis": "not_documented", "evidence": []}
        return GOOD[task.req.req_id]
    out = run(FallbackBackend(Fake("lora", fn=biased), Fake("base", GOOD)), live_counterfactual=True)
    r1 = out["requirements"][0]
    assert r1["bias_audit"]["counterfactual_flip"] and r1["bias_audit"]["affected_attribute"] == "nationality_signal"
    assert r1["requires_human_review"] and r1["final_decision"] == "MET"  # audit flags, never changes the decision
    fair = run(FallbackBackend(Fake("lora", GOOD), Fake("base", GOOD)), live_counterfactual=True)
    assert not any(x["bias_audit"]["counterfactual_flip"] for x in fair["requirements"])


def test_fallback_to_base_model_when_lora_down():
    lora, base = Fake("lora", down=True), Fake("base", GOOD)
    out = run(FallbackBackend(lora, base))
    for x in out["requirements"]:
        assert x["matcher_call"]["used"] == "fallback" and x["matcher_call"]["primary_error"]
        assert "matcher:fallback_model_used" in x["review_reasons"] and x["requires_human_review"]
    assert out["requirements"][0]["final_decision"] == "MET" and base.calls == 4


def test_both_models_down_never_invents_a_decision():
    out = run(FallbackBackend(Fake("lora", down=True), Fake("base", down=True)))
    for x in out["requirements"]:
        assert x["final_decision"] == "UNCERTAIN" and "matcher:backend_unavailable" in x["review_reasons"]


class FakeRetriever:
    """Retriever.search contract of the RAG team (rag/retrieval.py), without embeddings."""
    chunks = [{"doc_id": "http://data.europa.eu/esco/skill/maven", "source_type": "esco"},
              {"doc_id": "usajobs-1", "source_type": "job"}]

    def search(self, query, k=5, mode="hybrid", filters=None):
        assert mode == "dense" and "Senior Python developer" not in query  # CV text never sent to retrieval
        if filters.get("source_type") == "esco":
            c = {"doc_id": "http://data.europa.eu/esco/skill/maven", "source_type": "esco", "title": "Apache Maven",
                 "text": "Apache Maven. Also known as: Maven. Build automation tool.", "url": "u"}
            return {"status": "found", "results": [(c, 0.91)]}
        c = {"doc_id": "usajobs-1", "source_type": "job", "title": "Backend engineer", "text": "Requirements: Maven.", "url": "j"}
        return {"status": "found", "results": [(c, 0.88)]}


RAG = Path("/home/user/ragsrc-latest/rag")


@pytest.mark.skipif(not (RAG / "adapters.py").exists(), reason="RAG branch checkout not available")
def test_qdrant_knowledge_contract_with_job_chunks():
    q = QdrantKnowledge(rag_dir=RAG, retriever=FakeRetriever())
    req = JOB.requirements[1]
    refs = q.lookup(req, k=3)
    assert [(r.source_type, r.aliases) for r in refs] == [("esco", ["Maven"])]
    refs_job = q.lookup(req, k=3, job_id="usajobs-1")
    assert [r.source_type for r in refs_job] == ["esco", "job"] and refs_job[1].retrieval == "rag.qdrant.e5-small"
    out = Pipeline(Fake("lora", GOOD), q).run(CVX.model_dump(), {**JOB.model_dump(), "job_id": "usajobs-1"})
    assert {c["source_type"] for c in out["requirements"][1]["citations"]} == {"esco", "job"}


def test_factory_wiring_and_judge_fallback(tmp_path):
    p = build({"HS_JUDGE": "off", "HS_MATCHER_URL": "http://h1/v1", "HS_FALLBACK_URL": "http://h2/v1"}, knowledge=ESCO)
    b = p.matcher.backend
    assert isinstance(b, FallbackBackend) and b.primary.base_url == "http://h1/v1" and b.fallback.base_url == "http://h2/v1"
    assert b.primary.model.endswith("+lora") and p.judge is None
    assert judge_config({"HS_JUDGE_DIR": str(tmp_path / "missing")})[0] == PRETRAINED_JUDGE[0]
    if Path(FINETUNED_JUDGE[0]).exists():
        assert judge_config({})[1] == 0.85
