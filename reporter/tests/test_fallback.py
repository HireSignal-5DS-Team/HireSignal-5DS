"""SLM down / timeout / invalid JSON / hallucination: one retry, then the deterministic text, recorded in provenance.
A scripted SLM is labelled slm_mock, never 'slm'."""
import json

from reporter import to_html, to_markdown, write
from reporter.build import requirement_note
from reporter.slm import ScriptedSLM
from reporter.writer import slm_from_env

from _fixtures import pipeline_output

OUT = pipeline_output()
GOOD = {"r1": 'MET: the CV states "5 years of professional Python experience."',
        "r2": "MISSING: the CV states that it has not worked with Kubernetes so far.",
        "r3": "MISSING: the CV does not mention Terraform; a human reviewer must check it.",
        "r4": "UNCERTAIN: the evidence about Docker is partial."}
SUMMARY = "Of 4 requirements, 1 is MET, 2 are MISSING and 1 is UNCERTAIN."


def good(kind, facts, n):
    if kind == "summary":
        return json.dumps({"summary": SUMMARY})
    rid = next(r["req_id"] for r in OUT["requirements"] if r["requirement_text"] == facts["requirement"])
    return json.dumps({"note": GOOD[rid]})


def test_valid_scripted_output_is_used_and_labelled_mock():
    rep = write(OUT, slm=ScriptedSLM(good))
    assert rep.executive_summary.text == SUMMARY and rep.executive_summary.writer == "slm_mock"
    assert all(r.plain_note.writer == "slm_mock" and r.plain_note.attempts == 1 for r in rep.requirements)
    assert rep.provenance.any_mock and "MOCK" in rep.provenance.slm_status
    assert "scripted test double (MOCK, not a model)" in to_markdown(rep)


def _all_fallback(rep, reason):
    texts = [rep.executive_summary] + [r.plain_note for r in rep.requirements]
    assert all(t.writer == "deterministic_fallback" and t.attempts == 2 and len(t.rejections) == 2 for t in texts)
    assert all(reason in t.rejections[0] for t in texts)
    assert [r.plain_note.text for r in rep.requirements] == [requirement_note(r) for r in OUT["requirements"]]
    assert rep.provenance.sections_fallback == 5 and rep.provenance.sections_slm == 0
    assert "deterministic fallback (SLM text failed the fact check" in to_markdown(rep) and "deterministic fallback" in to_html(rep)


def test_slm_down():
    _all_fallback(write(OUT, slm=ScriptedSLM(lambda k, f, n: ConnectionError("refused"))), "slm_error:ConnectionError")


def test_slm_timeout():
    _all_fallback(write(OUT, slm=ScriptedSLM(lambda k, f, n: TimeoutError("30s"))), "slm_error:TimeoutError")


def test_invalid_json():
    _all_fallback(write(OUT, slm=ScriptedSLM(lambda k, f, n: "Sure! The candidate is great.")), "invalid_json")


def test_hallucination_in_every_section_never_reaches_the_report():
    bad = ScriptedSLM(lambda k, f, n: json.dumps({k: "MET: 12 years of Rust at Google; we recommend hiring."}))
    rep = write(OUT, slm=bad)
    _all_fallback(rep, "hiring_verdict")
    for doc in (to_markdown(rep), to_html(rep)):
        body = doc.split("## Provenance")[0] if "## Provenance" in doc else doc
        assert "Rust" not in body and "Google" not in body and "recommend hiring" not in body


def test_retry_is_corrective_and_can_succeed():
    def fn(kind, facts, n):  # first answer of each section hallucinates, the retry is faithful
        return json.dumps({kind: "MET: the CV shows Rust experience."}) if n % 2 else good(kind, facts, n)
    slm = ScriptedSLM(fn)
    rep = write(OUT, slm=slm)
    texts = [rep.executive_summary] + [r.plain_note for r in rep.requirements]
    assert all(t.writer == "slm_mock" and t.attempts == 2 and len(t.rejections) == 1 for t in texts)
    assert all(fb and "Rust" in fb for _, _, fb in slm.calls[1::2])  # the validator reasons are fed back
    assert all(fb is None for _, _, fb in slm.calls[0::2])


def test_env_off_and_unavailable(tmp_path):
    assert slm_from_env({}) == (None, "off")
    slm, status = slm_from_env({"HS_REPORTER_SLM": "on", "HS_REPORTER_MODEL_PATH": str(tmp_path / "nope.gguf")})
    assert slm is None and status.startswith("unavailable")
    rep = write(OUT, slm=slm, slm_status=status)
    assert rep.provenance.slm_status.startswith("unavailable") and rep.executive_summary.writer == "deterministic"
    import pytest
    with pytest.raises(Exception):
        slm_from_env({"HS_REPORTER_SLM": "required", "HS_REPORTER_MODEL_PATH": str(tmp_path / "nope.gguf")})
    with pytest.raises(ValueError):
        slm_from_env({"HS_REPORTER_SLM": "maybe"})
