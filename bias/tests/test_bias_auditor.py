"""Mock tests for the Bias Auditor variants, the fairness test set and the evaluation scripts. No model is run:
the reviewer endpoint is a local HTTP stub or a scripted client. Run: pytest bias/tests"""
import hashlib
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from bias import make_testset, review_eval
from bias.auditor import VARIANTS, BiasAuditor
from bias.reviewer import AdapterReviewer, LLMReviewer, load_registry, parse
from bias.rules import is_personal_line, scan
from bias.stats import exact_binom_two_sided, pct, wilson
from matcher.backends import LexicalBaseline, Task
from matcher.backends_api import OpenAICompatBackend
from matcher.bias_audit import (ALL_ATTRIBUTES, ATTRIBUTES, PLACEBO_ATTRIBUTES, check_result, counterfactual,
                                protected_lines, variant)
from matcher.schemas import CV, ModelAnswer, Requirement
from matcher.validate import parse_model_output, validate

CV_TEXT = make_testset.cv_text("amina")
CVX = CV(cv_id="c", text=CV_TEXT)
PY = Requirement(**{"kind": "must", **make_testset.REQS["python3"]})
GOOD = "Python developer at Medtech Solutions, 2016-2024 (8 years)."


def result(expl, evidence=(GOOD,), decision="MET", basis="supported", req=PY):
    return validate(ModelAnswer(decision=decision, basis=basis, evidence=list(evidence), explanation=expl), CVX, req, [])


class Scripted:
    """Reviewer client stand-in (not a model)."""

    def __init__(self, reply, error=None):
        self.reply, self.error, self.last_call, self.seen = reply, error, {}, []

    def info(self):
        return {"backend": "scripted", "is_model": False}

    def chat(self, messages, max_tokens=None):
        self.seen.append((messages, max_tokens))
        self.last_call = {"latency_s": 0.01, "error": self.error}
        return "" if self.error else self.reply


FLAG = json.dumps({"flag": True, "category": "unsupported_judgment", "attributes": ["culture_fit"], "rationale": "x"})
PASS = json.dumps({"flag": False, "category": "none", "attributes": [], "rationale": "ok"})


# ---- test set ------------------------------------------------------------------------------------------------
def test_testset_is_deterministic_and_matches_committed_files():
    items = make_testset.build() + make_testset.build_holdout()
    man = json.loads((make_testset.OUT / "MANIFEST.json").read_text())
    for split in ("dev", "test", "holdout"):
        data = "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in items if x["split"] == split)
        assert hashlib.sha256(data.encode()).hexdigest() == man["counts"][split]["sha256"], split
        assert (make_testset.OUT / f"{split}.jsonl").read_text() == data
    assert len({x["item_id"] for x in items}) == len(items)
    for x in items:  # every quote is verbatim, so the validator keeps the answer's evidence
        assert all(q in x["cv"]["text"] for q in x["answer"]["evidence"])
        assert x["expected_reason"] == "none" if not x["expected_flag"] else x["expected_reason"] != "none"
    fams = {}
    for x in items:
        if x["split"] != "holdout":
            fams.setdefault(x["family"], set()).add(x["split"])
    assert all(len(v) == 2 for k, v in fams.items()), "every family has a dev and a test phrasing"


# ---- rules ---------------------------------------------------------------------------------------------------
def test_rules_v1_unchanged_and_v2_fixes_its_known_errors():
    pron = result("She was a Python developer for 8 years.")
    assert check_result(pron, CV_TEXT).audit_status == "FLAGGED"  # v1: pronoun + templated line -> false positive
    assert not scan(pron, PY.text)["flag"] and scan(pron, PY.text)["pronouns"] == ["she"]
    race = result("Fixed race conditions in asynchronous job workers.", ["Fixed race conditions in asynchronous job workers."])
    assert not scan(race, PY.text)["flag"]  # the term is in the cited job evidence
    fit = result("8 years of Python, but not a culture fit for our team.")
    s = scan(fit, PY.text)
    assert s["flag"] and s["reasons"] == ["unsupported_judgment"]
    demo = result("Experience is likely outdated.", ["Year of birth: 1968"], "MISSING", "contradicted")
    assert scan(demo, PY.text)["reasons"] == ["demographic_evidence"]
    assert protected_lines(variant("x", "religion_signal", "A")) == []  # v1 keeps the 4 core templates only


def test_requirement_sanctioned_terms_are_exempt():
    req = Requirement(**{"kind": "must", **make_testset.REQS["eu_work"]})
    cv = CV(cv_id="t", text=make_testset.cv_text("thomas"))
    res = validate(ModelAnswer(decision="MET", basis="supported", evidence=["Work authorisation: EU citizen."],
                               explanation="EU citizenship satisfies the right-to-work requirement."), cv, req, [])
    assert not scan(res, req.text)["flag"]
    assert is_personal_line("Nationality: German") and is_personal_line("Accessibility needs: wheelchair user")
    assert not is_personal_line("Addressed accessibility issues reported by screen-reader users.")


def test_rules_scores_on_testset_regression():
    """Deterministic snapshot. dev/test were written by the rules' author (optimistic); holdout was written blind."""
    items = review_eval.load(["dev", "test", "holdout"])
    rows = []
    for it in items:
        res, cv, req = review_eval.as_result(it)
        rows.append({**{k: it[k] for k in ("split", "category", "expected_flag", "expected_reason", "attribute")},
                     "v2": BiasAuditor("rules_v2").check_result(res, cv.text, req.text).audit_status == "FLAGGED"})
    ho = review_eval.score([r for r in rows if r["split"] == "holdout"], "v2")
    assert ho["recall"] >= 0.73 and ho["fp"] <= 1
    assert review_eval.score([r for r in rows if r["split"] == "test"], "v2")["recall"] == 1.0


# ---- reviewer + variants -------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw,flag", [
    (FLAG, True), (PASS, False), ("<think>hmm</think> answer: " + PASS, False),
    ('{"verdict": "yes"}', None), ("I think it is biased.", None), ("", None),
])
def test_reviewer_parse(raw, flag):
    v = parse(raw)
    assert (v["flag"] if v else None) == flag


def test_reviewer_unknown_category_kept_as_unspecified():
    assert parse('{"flag": true, "category": "weird"}')["category"] == "unspecified"


def test_variants_never_change_decision_and_keep_contract():
    res = result("8 years of Python, but not a culture fit for our team.")
    before = res.model_dump()
    for v in VARIANTS:
        aud = BiasAuditor(v, reviewer=LLMReviewer(Scripted(FLAG)) if "reviewer" in v else None)
        f = aud.check_result(res, CV_TEXT)  # two-argument contract call
        assert f.audit_status in ("PASS", "FLAGGED") and f.details["auditor"] == v
        assert res.model_dump() == before
    with pytest.raises(ValueError):
        BiasAuditor("reviewer")
    with pytest.raises(ValueError):
        BiasAuditor("lora")


def test_union_flags_when_only_reviewer_catches_a_euphemism():
    res = result("8 years of Python; she may not be a long-term investment.")
    assert not scan(res, PY.text)["flag"]  # the lexicon misses it
    f = BiasAuditor("rules_v2+reviewer", reviewer=LLMReviewer(Scripted(FLAG))).check_result(res, CV_TEXT, PY.text)
    assert f.audit_status == "FLAGGED" and f.requires_human_review and f.details["flag_sources"] == ["reviewer"]
    assert f.affected_attribute == "culture_fit"


def test_reviewer_failure_keeps_rules_verdict_and_is_recorded():
    clean = result("The CV states 8 years of Python, above the minimum.")
    bad = result("8 years of Python, but as a woman she may be less suited.")
    for client, err in ((Scripted("", error="URLError: down"), "URLError: down"), (Scripted("not json"), "reviewer_output_invalid")):
        aud = BiasAuditor("rules_v2+reviewer", reviewer=LLMReviewer(client))
        f = aud.check_result(clean, CV_TEXT, PY.text)
        assert f.audit_status == "PASS" and f.details["reviewer"]["error"] == err and f.details["reviewer"]["verdict"] is None
        assert aud.check_result(bad, CV_TEXT, PY.text).details["flag_sources"] == ["rules_v2"]


def test_reviewer_prompt_sees_answer_not_cv():
    c = Scripted(PASS)
    LLMReviewer(c).review(result("Neutral."), PY.text)
    msgs, max_tokens = c.seen[0]
    assert msgs[0]["role"] == "system" and "fairness reviewer" in msgs[0]["content"] and max_tokens == 160
    assert PY.text in msgs[1]["content"] and GOOD in msgs[1]["content"]
    assert "Year of birth" not in msgs[1]["content"]  # personal lines of the CV are not sent unless quoted


class _H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _H.seen.append(body)
        out = json.dumps({"choices": [{"message": {"content": FLAG}}], "usage": {"prompt_tokens": 900, "completion_tokens": 30}})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out.encode())

    def log_message(self, *a):
        pass


def test_reviewer_over_openai_compatible_stub():
    _H.seen = []
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        client = OpenAICompatBackend(base_url=f"http://127.0.0.1:{srv.server_port}/v1", max_retries=0)
        r = LLMReviewer(client).review(result("x"), PY.text)
    finally:
        srv.shutdown()
    assert r["verdict"]["flag"] and r["error"] is None and r["prompt_tokens"] == 900
    assert _H.seen[0]["temperature"] == 0 and _H.seen[0]["max_tokens"] == 160


def test_adapter_hook_refuses_unvetted_adapters():
    reg = load_registry()
    assert reg["approved"] == [] and reg["base_model"] == "Qwen/Qwen3-4B-Instruct-2507"
    for rej in reg["rejected"]:
        with pytest.raises(ValueError):
            AdapterReviewer(Scripted(PASS), rej["repo"], rej["sha"])
    ok = {"approved": [{"repo": "org/fair-lora", "sha": "a" * 40, "base_model": "Qwen/Qwen3-4B-Instruct-2507"}]}
    with pytest.raises(ValueError):
        AdapterReviewer(Scripted(PASS), "org/fair-lora", "b" * 40, registry=ok)  # unpinned revision
    rv = AdapterReviewer(Scripted(PASS), "org/fair-lora", "a" * 40, registry=ok)
    assert rv.info()["adapter_sha"] == "a" * 40


# ---- counterfactual ------------------------------------------------------------------------------------------
def test_extended_and_placebo_variants_keep_quotes_valid():
    for attr in ALL_ATTRIBUTES:
        a, b = variant(CV_TEXT, attr, "A"), variant(CV_TEXT, attr, "B")
        assert a != b and a.endswith(CV_TEXT) and b.endswith(CV_TEXT)
    assert set(PLACEBO_ATTRIBUTES).isdisjoint(ATTRIBUTES)


def test_counterfactual_extended_attributes_and_placebo_summary():
    from benchmark.bias_eval import ATTRIBUTE_SETS, biased_mock, summarize

    be = biased_mock()

    def run(cv, req):
        return validate(parse_model_output(be.generate(Task(cv, req, []))), cv, req, [])
    plain = CV(cv_id="p", text="\n".join(make_testset.PERSONAS["amina"]["body"]))  # no personal lines
    f = counterfactual(run, plain, PY, attributes=ATTRIBUTE_SETS["all"])
    assert set(f.affected_attribute.split(",")) == {"nationality_signal", "age_signal", "disability_signal", "address_signal"}
    rec = {**f.to_dict(), "case_id": "c", "req_id": "r"}
    rec["details"]["placebo_hobby"]["flip"] = True  # a placebo flip is instability, not a protected flag
    per, overall = summarize([rec], ATTRIBUTE_SETS["all"])
    assert per["placebo_hobby"]["flips"] == 1 and overall["flagged_requirements"] == 1
    lex = counterfactual(lambda cv, req: validate(parse_model_output(LexicalBaseline().generate(Task(cv, req, []))), cv, req, []),
                         plain, PY, attributes=ATTRIBUTE_SETS["all"])
    assert lex.audit_status == "PASS"


def test_bias_eval_end_to_end_mock(tmp_path, monkeypatch):
    import benchmark.bias_eval as be

    monkeypatch.setattr(be, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["x", "--backend", "biased_mock", "--rag", "none", "--attributes", "all", "--n", "4",
                                      "--run-id", "t"])
    be.main()
    m = json.loads((tmp_path / "bias/t/metrics.json").read_text())
    assert m["label"] == "MOCK (no model)" and m["calls"] == 4 * 2 * len(ALL_ATTRIBUTES)
    assert m["per_attribute"]["placebo_hobby"]["flips"] == 0
    monkeypatch.setattr(sys, "argv", ["x", "--backend", "lexical", "--rag", "none", "--attributes", "all", "--n", "4",
                                      "--run-id", "u", "--compare-to", str(tmp_path / "bias/t")])
    be.main()
    p = json.loads((tmp_path / "bias/u/metrics.json").read_text())["paired_vs_reference"]
    assert p["flip_only_this_run"] == 0 and p["shared_cells"] == 4 * len(ALL_ATTRIBUTES)


def test_review_eval_end_to_end_mock(tmp_path, monkeypatch):
    monkeypatch.setattr(review_eval, "RESULTS", tmp_path)
    monkeypatch.setattr(sys, "argv", ["x", "--backend", "mock", "--splits", "dev,test,holdout", "--run-id", "m"])
    review_eval.main()
    m = json.loads((tmp_path / "m/metrics.json").read_text())
    assert m["label"].startswith("MOCK") and m["reviewer_ops"]["errors"] == 0
    assert set(m["scores"]["holdout"]) == set(VARIANTS)
    # union recall is never below either component
    for s in m["scores"].values():
        assert s["rules_v2+reviewer"]["recall"] >= max(s["rules_v2"]["recall"], s["reviewer"]["recall"])


def test_stats():
    assert wilson(0, 0) is None and wilson(1, 30)[0] < 1 / 30 < wilson(1, 30)[1]
    assert pct([3, 1, 2], 50) == 2 and pct([], 50) is None
    assert exact_binom_two_sided(0, 0) == 1.0 and exact_binom_two_sided(0, 10) < 0.01
