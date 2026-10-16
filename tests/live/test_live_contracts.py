"""LIVE validation of the real Matcher (LoRA primary, base fallback) against the same contracts as tests/qa/.
Skipped unless HS_LIVE=1 and the servers answer (see conftest.py). Outputs and provenance go to HS_LIVE_OUT.

System-level safety contract checked on real outputs: a false-MET trap must never come out as
"MET without human review"; failures must be UNCERTAIN + review; provenance must name the model that answered.
These are small adversarial probes, not the 202-requirement evaluation (that is benchmark/run.py on val).
"""
import os

import pytest
from _qa_support import CVX, JOB, defect, provenance_problems
from live_cases import POSITIVES, TRAPS, job_for

from matcher import CV
from matcher.backends_api import FallbackBackend, OpenAICompatBackend
from matcher.bias_audit import counterfactual


class Recording:
    """Wraps the live backend to keep the raw text of every call (for results.jsonl)."""

    def __init__(self, inner):
        self.inner, self.raws = inner, []

    def info(self):
        return self.inner.info()

    @property
    def last_call(self):
        return getattr(self.inner, "last_call", {})

    def generate(self, task):
        raw = self.inner.generate(task)
        self.raws.append(raw)
        return raw


@pytest.fixture(scope="module")
def live(pipeline):
    if not isinstance(pipeline.matcher.backend, Recording):
        pipeline.matcher.backend = Recording(pipeline.matcher.backend)
    return pipeline


def run_case(live, recorder, test, case):
    cv = CV(cv_id=case["id"], text=case["cv"])
    out = live.run(cv.model_dump(), job_for(case).model_dump())
    row = out["requirements"][0]
    recorder(test, case["id"], row, raw=live.matcher.backend.raws[-1], expect=case.get("expect"))
    return row


def test_servers_identify_their_models(servers, recorder):
    ids = [m.get("id") for m in (servers["primary"] or {}).get("data", [])]
    assert ids, "primary /models lists no model"
    recorder("server_identity", "primary", {"models": ids})


@pytest.mark.parametrize("case", TRAPS, ids=[c["id"] for c in TRAPS])
def test_false_met_trap_is_never_an_unreviewed_met(live, recorder, case):
    row = run_case(live, recorder, "trap", case)
    assert not (row["final_decision"] == "MET" and not row["requires_human_review"]), \
        f"{case['id']}: unreviewed MET on a trap; raw model decision {row['model_decision']}"


@pytest.mark.parametrize("case", POSITIVES, ids=[c["id"] for c in POSITIVES])
def test_positive_control_is_not_rejected(live, recorder, case):
    """Guards against a 'safe' model that never says MET: a clear match must not come out MISSING."""
    row = run_case(live, recorder, "positive", case)
    assert row["final_decision"] != "MISSING"


def test_evidence_is_verbatim_and_spans_exact(live, recorder):
    out = live.run(CVX.model_dump(), JOB.model_dump())
    for row in out["requirements"]:
        recorder("full_job", row["req_id"], row)
        assert all(CVX.text[a:b] == q for q, (a, b) in zip(row["evidence"], row["evidence_spans"]))
        assert row["final_decision"] != "MET" or row["evidence"]


@defect("QA-028", "S2")
def test_live_explanations_name_the_requirement(live, recorder):
    from _qa_support import explanation_problems

    out = live.run(CVX.model_dump(), JOB.model_dump())
    reqs = {r.req_id: r for r in JOB.requirements}
    problems = {r["req_id"]: explanation_problems(r, reqs[r["req_id"]]) for r in out["requirements"]}
    recorder("explanations", "full_job", {"explanations": {r["req_id"]: r["explanation"] for r in out["requirements"]},
                                          "problems": problems})
    assert all(not p for p in problems.values()), problems


def test_deterministic_at_temperature_zero(live):
    case = POSITIVES[0]
    raws = []
    for _ in range(2):
        run_case(live, lambda *a, **k: None, "determinism", case)
        raws.append(live.matcher.backend.raws[-1])
    assert raws[0] == raws[1]


def test_provenance_names_the_answering_model(live, recorder):
    out = live.run(CVX.model_dump(), JOB.model_dump())
    for row in out["requirements"]:
        assert row["matcher_call"].get("used") in ("primary", "fallback", None)
        if row["matcher_call"].get("used") == "fallback":
            assert row["requires_human_review"]
    recorder("provenance_rows", "full_job", {"backend": out["backend"], "knowledge": out["knowledge"]})


@defect("QA-014", "S2")
def test_provenance_is_complete(live):
    rep = live.matcher.match(CVX, JOB.model_copy(update={"requirements": JOB.requirements[:1]}))
    assert provenance_problems(rep.backend) == []


def test_fallback_serves_when_primary_is_unreachable(servers, recorder):
    if servers["fallback"] is None:
        pytest.skip("LIVE: fallback server does not answer")
    from matcher.knowledge import NoKnowledge
    from matcher.pipeline import Pipeline

    dead = OpenAICompatBackend(base_url="http://127.0.0.1:9/v1", model="dead", timeout=2, max_retries=0)
    base = OpenAICompatBackend(base_url=os.environ.get("HS_FALLBACK_URL", "http://127.0.0.1:8080/v1"),
                               model=os.environ.get("HS_FALLBACK_MODEL", "Qwen/Qwen3-4B-Instruct-2507"))
    out = Pipeline(FallbackBackend(dead, base), NoKnowledge()).run(CVX.model_dump(), JOB.model_dump())
    for row in out["requirements"]:
        recorder("fallback", row["req_id"], row)
        assert row["matcher_call"]["used"] == "fallback" and row["requires_human_review"]


def test_counterfactual_flips_are_flagged(live, recorder):
    """Records flips of the real Matcher on two requirements; the contract is only that a flip is FLAGGED.
    Flip rates are S4's measurement (benchmark/bias_eval.py), not a pass/fail criterion here."""
    m = live.matcher
    for req in JOB.requirements[:2]:
        f = counterfactual(lambda c, q: m.match_requirement(c, q)[0], CVX, req)
        recorder("counterfactual", req.req_id, f.to_dict())
        assert (f.audit_status == "FLAGGED") == bool(f.counterfactual_flip)


def test_judge_flags_negated_met_when_enabled(live, recorder):
    if live.judge is None:
        pytest.skip("LIVE: Judge not loaded (HS_LIVE_JUDGE=1 to include it)")
    from _qa_support import check

    res = check("MET", "supported", ["Kubernetes in production"], CVX, JOB.requirements[2])
    f = live.judge.judge_many([(res, CVX, JOB.requirements[2])])[0]
    recorder("judge_negation", "r3-partial", f.to_dict())
    assert f.judge_verdict != "PASS" and res.decision == "MET"
