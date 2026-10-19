"""T12 Report Writer: fact checker, template, retry -> template fallback, schema, /report contract (no real LLM)."""
import copy
import glob
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from services import api
from services.report.checker import check
from services.report.record import build_record
from services.report.template import render
from services.report.writer import FALLBACK_FLAG, write_report

ROOT = Path(__file__).resolve().parents[1]
REQS = [
    {"req_id": "r1", "kind": "must", "text": "3+ years of Python", "decision": "MET",
     "quotes": ["Python developer since 2019, 5 years in data pipelines."], "judge": "PASS", "skill_terms": ["Python"],
     "min_years": 3, "evidence_years": 5},
    {"req_id": "r2", "kind": "must", "text": "Experience with Apache Spark", "decision": "MISSING", "quotes": [],
     "judge": "PASS", "skill_terms": ["Spark"]},
    {"req_id": "r3", "kind": "nice", "text": "Docker", "decision": "UNCERTAIN", "quotes": [],
     "review_reasons": ["match:low_confidence"], "skill_terms": ["Docker"]},
]
RECORD = build_record(REQS, {"outcome": "reject", "score": 40, "rule": "1 reject", "reasons": ["r2: must-have MISSING"]},
                      job_title="Data Engineer")


def good():
    return render(RECORD)


def test_template_passes_the_checker():
    assert check(RECORD, good()) == []


def test_template_passes_the_checker_on_every_evaluation_record():
    files = glob.glob(str(ROOT / "data/processed/report_records/*/*.json"))
    if not files:
        pytest.skip("records not generated")
    for f in files:
        rec = json.loads(Path(f).read_text(encoding="utf-8"))
        assert check(rec, render(rec)) == [], f


@pytest.mark.parametrize("edit,error", [
    (lambda r: r["requirements"][0].update(quote="Python developer since 2015"), "quote is not in its verified"),
    (lambda r: r.update(recruiter_summary=r["recruiter_summary"] + ' The CV says "led a team of 12".'), "quoted text"),
    (lambda r: r["requirements"][1].update(decision="MET"), "decision MET but the record says MISSING"),
    (lambda r: r.update(recruiter_summary=r["recruiter_summary"].replace("score is 40", "score is 72")), "number 72"),
    (lambda r: r.update(candidate_letter=r["candidate_letter"].replace("Dear candidate", "Dear John Smith")),
     "a personal name"),
    (lambda r: r.update(recruiter_summary=r["recruiter_summary"] + " The candidate is married."), "protected identity"),
    (lambda r: r.update(recruiter_summary=r["recruiter_summary"] + " [NAME] applied."), "placeholder [NAME]"),
    (lambda r: r["requirements"].pop(1), "must requirement r2 dropped"),
    (lambda r: r["requirements"].append({"req_id": "r9", "decision": "MET", "quote": "", "line": "x"}),
     "invented requirement r9"),
    (lambda r: r.update(candidate_letter=r["candidate_letter"] + " Our bias check passed."), "internals"),
    (lambda r: r.update(candidate_letter="Dear candidate, we will not move forward. Kind regards"),
     "without the right to a human review"),
    (lambda r: r.update(recruiter_summary="The candidate is invited."), "summary does not state the outcome"),
    (lambda r: r.update(flags_for_recruiter=[]), "flag dropped: low_confidence"),
])
def test_checker_catches(edit, error):
    rep = copy.deepcopy(good())
    edit(rep)
    errors = check(RECORD, rep)
    assert any(error in e for e in errors), errors


def test_review_case_must_not_have_a_letter():
    rec = copy.deepcopy(RECORD) | {"outcome": "review"}
    rep = render(rec)
    assert check(rec, rep) == []
    rep["candidate_letter"] = "Dear candidate, we will not move forward."
    assert "candidate letter for a review case" in check(rec, rep)


def _llm(*answers):
    """A fake llama-server: returns the given JSON answers in order; records the requests."""
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        content = answers[min(len(seen), len(answers)) - 1]
        return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]})
    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_two_failures_fall_back_to_the_template():
    bad = copy.deepcopy(good())
    bad["requirements"][1]["decision"] = "MET"
    client, seen = _llm(json.dumps(bad), json.dumps(bad))
    out = write_report(RECORD, client=client, base_url="http://x/v1", model="m")
    assert out["source"] == "template" and out["attempts"] == 2 and out["info_flags"] == [FALLBACK_FLAG]
    assert out["report"] == render(RECORD) and len(seen) == 2
    assert "decision MET but the record says MISSING" in seen[1]["messages"][-1]["content"]  # errors sent back
    assert seen[0]["response_format"]["schema"]["required"] and seen[0]["lora"] == [{"id": 0, "scale": 0}]


def test_retry_fixes_the_report():
    bad = copy.deepcopy(good())
    bad["requirements"].pop(1)
    client, seen = _llm(json.dumps(bad), json.dumps(good()))
    out = write_report(RECORD, client=client, base_url="http://x/v1", model="m")
    assert out["source"] == "llm" and out["attempts"] == 2 and out["retry_errors"] == [] and out["info_flags"] == []


def test_invalid_json_or_missing_keys_count_as_errors():
    client, _ = _llm("not json", json.dumps({"recruiter_summary": "x"}))
    out = write_report(RECORD, client=client, base_url="http://x/v1", model="m")
    assert out["first_errors"] == ["the answer is not valid JSON"]
    assert out["retry_errors"] == ["the answer misses keys of the output schema"] and out["source"] == "template"


def test_report_endpoint_contract(monkeypatch):
    import services.report.writer as w
    monkeypatch.setattr(w, "write_report", lambda record, **k: {
        "report": render(record), "source": "template", "attempts": 0, "first_errors": [], "retry_errors": [],
        "info_flags": [FALLBACK_FLAG], "model": "m"})
    body = {"requirements": REQS, "outcome": {"outcome": "reject", "score": 40, "rule": "1", "reasons": []},
            "reader": {"mode": "late", "review_reasons": []}, "bias": {"review_reasons": [], "swap": {"ran": True}},
            "job_title": "Data Engineer", "cv_id": "cv-0000abcd"}
    out = TestClient(api.app).post("/report", json=body)
    assert out.status_code == 200, out.text
    j = out.json()
    assert set(j["report"]) == {"recruiter_summary", "requirements", "candidate_letter", "flags_for_recruiter"}
    assert j["source"] == "template" and j["cv_id"] == "cv-0000abcd"
    assert TestClient(api.app).post("/report", json=body | {"name": "John"}).status_code == 422  # strict contract


def test_n8n_report_writer_node_sends_the_report_contract():
    from services.contracts import ReportIn, ReportRequirement
    wf = json.loads((ROOT / "n8n/hiresignal_v1.json").read_text(encoding="utf-8"))
    node = next(n for n in wf["nodes"] if n["name"] == "Report Writer")
    assert node["parameters"]["url"].endswith("/report")
    body = node["parameters"]["jsonBody"]
    for key in ReportIn.model_fields:
        assert f"{key}:" in body, key
    for key in ReportRequirement.model_fields:
        assert f"{key}:" in body, key
    assert wf["connections"]["HTTP /outcome"]["main"][0][0]["node"] == "Report Writer"
    assert wf["connections"]["Report Writer"]["main"][0][0]["node"] == "Result"


# ------------------------------------------------------------------ T13: two new rules + human decisions ---

def test_line_must_start_with_its_decision_word():
    rep = copy.deepcopy(good())
    rep["requirements"][1]["line"] = "Spark is not in the CV."
    assert any("line does not start with 'Missing'" in e for e in check(RECORD, rep))


def test_line_that_contradicts_its_decision_is_caught():
    rep = copy.deepcopy(good())
    rep["requirements"][0]["line"] = "Met: Python is mentioned, but no evidence of 3 years is found."
    assert any("line contradicts its decision (MET)" in e for e in check(RECORD, rep))
    rep["requirements"][0]["line"] = "Met: the CV shows 5 years of Python."
    assert check(RECORD, rep) == []


def test_a_quote_or_requirement_text_inside_a_line_does_not_trigger_the_contradiction_rule():
    reqs = copy.deepcopy(REQS)
    reqs[0]["quotes"] = ["Python bugs not found in production for 5 years."]
    rec = build_record(reqs, {"outcome": "reject", "score": 40, "rule": "1", "reasons": []})
    rep = render(rec)
    rep["requirements"][0]["line"] = "Met: the CV says Python bugs not found in production for 5 years."
    assert not any("contradicts" in e for e in check(rec, rep))


def test_reject_letter_may_name_only_missing_must_haves():
    rep = copy.deepcopy(good())
    rep["candidate_letter"] = rep["candidate_letter"].replace("Apache Spark.", "Apache Spark; Docker.")
    assert any("names r3 (nice, UNCERTAIN)" in e for e in check(RECORD, rep))
    rep = copy.deepcopy(good())
    rep["candidate_letter"] = rep["candidate_letter"].replace("Apache Spark.", "Apache Spark and Python.")
    assert any("names r1 (must, MET)" in e for e in check(RECORD, rep))


def test_human_reject_letter_rules():
    rec = copy.deepcopy(RECORD) | {"decided_by": "human"}
    rep = render(rec)
    assert check(rec, rep) == [] and "automated" not in rep["candidate_letter"].lower()
    assert "GDPR" not in rep["candidate_letter"]  # no "right to a human review" after a human decision
    rep["candidate_letter"] += " This decision was prepared with an automated system."
    assert "human-decided reject letter calls the decision automated" in check(rec, rep)


def test_human_reject_may_name_unclear_must_haves():
    reqs = copy.deepcopy(REQS)
    reqs[1] |= {"decision": "UNCERTAIN"}
    rec = build_record(reqs, {"outcome": "reject", "score": 60, "rule": "x", "reasons": []}, decided_by="human")
    rep = render(rec)
    assert "Apache Spark" in rep["candidate_letter"] and check(rec, rep) == []
    gate = copy.deepcopy(rec) | {"decided_by": "gate"}
    gate_rep = copy.deepcopy(rep)
    gate_rep["candidate_letter"] = (render(gate)["candidate_letter"].rstrip(".") +
                                    " Your CV does not clearly show experience with Apache Spark.")
    assert any("names r2 (must, UNCERTAIN)" in e for e in check(gate, gate_rep))  # only a human may give unclear ones


def test_report_endpoint_passes_decided_by(monkeypatch):
    import services.report.writer as w
    seen = {}
    monkeypatch.setattr(w, "write_report", lambda record, **k: seen.update(record) or {
        "report": render(record), "source": "template", "attempts": 0, "first_errors": [], "retry_errors": [],
        "info_flags": [], "model": "m"})
    body = {"requirements": REQS, "outcome": {"outcome": "reject", "score": 40, "rule": "x", "reasons": []},
            "decided_by": "human"}
    out = TestClient(api.app).post("/report", json=body).json()
    assert seen["decided_by"] == "human" and "automated" not in out["report"]["candidate_letter"].lower()


def test_n8n_human_decision_gets_a_checked_letter():
    wf = json.loads((ROOT / "n8n/hiresignal_v1.json").read_text(encoding="utf-8"))
    nodes = {n["name"]: n for n in wf["nodes"]}
    node = nodes["Report Writer (human decision)"]
    assert node["parameters"]["url"].endswith("/report") and "decided_by: 'human'" in node["parameters"]["jsonBody"]
    assert wf["connections"]["Decided by human"]["main"][0][0]["node"] == "Report Writer (human decision)"
    assert wf["connections"]["Report Writer (human decision)"]["main"][0][0]["node"] == "Human letter"
    assert wf["connections"]["Human letter"]["main"][0][0]["node"] == "Outbox letter"
    assert "r.human_report.candidate_letter" in nodes["Outbox letter"]["parameters"]["jsCode"]
