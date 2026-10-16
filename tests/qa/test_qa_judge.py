"""NLI Judge behaviour (matcher/judge.py, owner S5). MOCK: NLI probabilities come from a keyword stand-in, so these
tests check the Judge's premise construction, verdict mapping and failure handling, not DeBERTa's accuracy (that is
benchmark/judge_eval.py on saved predictions, and tests/live/ in window 1).
"""
from _qa_support import CVX, JOB, Scripted, check, req

from matcher import CV
from matcher.judge import NLIJudge
from matcher.pipeline import Pipeline, aggregate
from matcher.bias_audit import check_result
from matcher.tests.test_pipeline import FakeJudge

NEG = ("never", "no experience", "not worked", "has not")


def keyword_nli(premise, hyp, window=None):
    """Toy NLI: a negation cue + the hypothesis skill -> contradiction; the skill alone -> entailment; else neutral.
    window: characters the model 'sees' (the real tokenizer truncates the premise to max_length tokens)."""
    p = (premise if window is None else premise[:window]).casefold()
    skill = next((s for s in ("kubernetes", "kafka", "python", "maven", "rust") if s in hyp.casefold()), None)
    lines = [ln for ln in p.splitlines() if skill and skill in ln]
    if any(not any(n in ln for n in NEG) for ln in lines):
        return {"entailment": 0.93, "neutral": 0.05, "contradiction": 0.02}
    if lines:
        return {"entailment": 0.02, "neutral": 0.03, "contradiction": 0.95}
    return {"entailment": 0.05, "neutral": 0.9, "contradiction": 0.05}


K8S = JOB.requirements[2]


def test_negated_quote_as_met_is_flagged_and_decision_kept():
    res = check("MET", "supported", ["Never used Kubernetes in production; deployments ran on managed VMs."], CVX, K8S)
    f = FakeJudge(keyword_nli).judge_many([(res, CVX, K8S)])[0]
    assert f.judge_verdict == "FAIL" and f.judge_disagrees and f.requires_human_review
    row = aggregate(res, check_result(res, CVX.text), f)
    assert row["final_decision"] == "MET" and "judge:disagrees" in row["review_reasons"]


def test_contradiction_supported_by_quote_passes():
    res = check("MISSING", "contradicted", ["Never used Kubernetes in production; deployments ran on managed VMs."], CVX, K8S)
    assert FakeJudge(keyword_nli).judge_many([(res, CVX, K8S)])[0].judge_verdict == "PASS"


def test_not_documented_but_cv_shows_skill_is_flagged():
    py = req("r1", "Python development", skill_terms=["Python"])
    res = check("MISSING", "not_documented", [], CVX, py)
    f = FakeJudge(keyword_nli).judge_many([(res, CVX, py)])[0]
    assert f.judge_verdict == "FAIL" and res.decision == "MISSING"


def test_partial_quote_hiding_a_negation_is_flagged():
    """QA-017 (fixed in judge.py): the quote 'Kubernetes in production' is verbatim, but its CV line starts with
    'Never used'. The Judge must read the quote in its line context, not the bare fragment."""
    res = check("MET", "supported", ["Kubernetes in production"], CVX, K8S)
    assert res.decision == "MET"  # the validator lets it through (QA-002)
    f = FakeJudge(keyword_nli).judge_many([(res, CVX, K8S)])[0]
    assert f.judge_verdict == "FAIL" and f.requires_human_review and res.decision == "MET"


def test_long_cv_not_documented_check_reads_the_whole_cv():
    """QA-018 (fixed in judge.py): for MISSING/not_documented the premise is the whole CV; a 512-token model only
    sees its beginning. A skill stated at the end of a long CV must still be found."""
    filler = "\n".join(f"- Delivered project {i} on time with the team." for i in range(120))
    cv = CV(cv_id="long", text=f"Experience\n{filler}\n- 4 years of Rust systems programming.")
    rust = req("r8", "Rust programming", skill_terms=["Rust"])
    res = check("MISSING", "not_documented", [], cv, rust)
    judge = FakeJudge(lambda p, h: keyword_nli(p, h, window=1500))
    assert judge.judge_many([(res, cv, rust)])[0].judge_verdict == "FAIL"


def test_premise_chunks_fit_the_model_window():
    filler = "\n".join(f"- Line {i} with some words in it." for i in range(400))
    cv = CV(cv_id="long", text=filler)
    res = check("MISSING", "not_documented", [], cv, req("r8", "Rust", skill_terms=["Rust"]))
    kind, premises = FakeJudge(keyword_nli).premises(res, cv)
    assert kind == "cv" and len(premises) > 1
    assert all(len(p) <= NLIJudge.max_premise_chars for p in premises)
    assert "".join(p.replace("\n", "") for p in premises) == cv.text.replace("\n", "")  # nothing dropped


def test_judge_failure_does_not_crash_the_pipeline_or_change_decisions():
    """QA-019 (fixed in judge.py): an NLI error becomes an UNCERTAIN finding (review), never a crash or a decision."""
    class Broken(FakeJudge):
        def probs(self, pairs, batch_size=16):
            raise RuntimeError("CUDA out of memory")

    out = Pipeline(Scripted(), _NoRefs(), judge=Broken(keyword_nli)).run(CVX.model_dump(), JOB.model_dump())
    plain = Pipeline(Scripted(), _NoRefs()).run(CVX.model_dump(), JOB.model_dump())
    assert [r["final_decision"] for r in out["requirements"]] == [r["final_decision"] for r in plain["requirements"]]
    for r in out["requirements"]:
        if r["judge"]["judge_verdict"] != "NOT_APPLICABLE":
            assert r["judge"]["judge_verdict"] == "UNCERTAIN" and "RuntimeError" in r["judge"]["error"]
            assert r["requires_human_review"] and "judge:uncertain" in r["review_reasons"]


def test_uncertain_is_not_applicable_and_already_reviewed():
    res = check("UNCERTAIN", "ambiguous", [], CVX, K8S)
    f = FakeJudge(keyword_nli).judge_many([(res, CVX, K8S)])[0]
    assert f.judge_verdict == "NOT_APPLICABLE" and f.requires_human_review


class _NoRefs:
    name = "none"

    def lookup(self, req, k=3, job_id=None):
        return []


def test_judge_eval_uses_the_same_premises_as_the_pipeline():
    """benchmark/judge_eval.py must score exactly what the pipeline Judge sees (else its calibration is off)."""
    from types import SimpleNamespace

    from benchmark.judge_eval import probs_for, verdicts

    judge = FakeJudge(keyword_nli)
    cases = [("MET", "supported", ["Kubernetes in production"], K8S),
             ("MISSING", "not_documented", [], req("r1", "Python", skill_terms=["Python"])),
             ("UNCERTAIN", "ambiguous", [], K8S)]
    items, live = [], []
    for d, b, ev, rq in cases:
        res = check(d, b, ev, CVX, rq)
        live.append(judge.judge_many([(res, CVX, rq)])[0])
        items.append(({}, SimpleNamespace(decision=res.decision, basis=res.basis, evidence=res.evidence), CVX, rq))
    offline = verdicts(judge, items, probs_for(judge, items), 0.5)
    assert [f.judge_verdict for f in offline] == [f.judge_verdict for f in live] == ["FAIL", "FAIL", "NOT_APPLICABLE"]
