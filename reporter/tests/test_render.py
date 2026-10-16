"""Deterministic renderer: schema, sections, escaping, labels, disclaimer, provenance."""
import json
from pathlib import Path

import jsonschema
import pytest

from reporter import DISCLAIMER, Report, to_html, to_markdown, write, write_files
from reporter.schema import export_json_schema

from _fixtures import JOB, pipeline_output


@pytest.fixture(scope="module")
def out():
    return pipeline_output()


def test_report_validates_against_exported_schema(out, tmp_path):
    rep = write(out, job_title=JOB["title"])
    schema = json.loads((Path(__file__).parents[1] / "json_schemas/Report.schema.json").read_text())
    jsonschema.validate(rep.model_dump(mode="json"), schema)
    export_json_schema(tmp_path)  # the committed schema is up to date
    assert json.loads((tmp_path / "Report.schema.json").read_text()) == schema
    assert Report.model_validate_json(rep.model_dump_json()) == rep


def test_sections_come_from_the_pipeline_fields_only(out):
    rep = write(out)
    assert [r.req_id for r in rep.requirements] == ["r1", "r2", "r3", "r4"]
    assert [r.decision for r in rep.requirements] == [r["final_decision"] for r in out["requirements"]]
    r1, r2, r3, _ = rep.requirements
    assert r1.evidence[0].quote == "5 years of professional Python experience."
    a, b = r1.evidence[0].span
    assert list(out["requirements"][0]["evidence_spans"][0]) == [a, b]
    assert r2.knowledge_shown and r2.knowledge_shown[0].label == "knowledge shown to the model"
    assert r3.requires_human_review and "validator:must_have_absence_of_evidence" in r3.review_reasons
    assert rep.overview.counts == {"MET": 1, "MISSING": 2, "UNCERTAIN": 1} and rep.overview.must_total == 3
    assert rep.overview.job_title is None  # not in the pipeline output; only when the caller gives it
    assert all(r.judge.verdict == "not run" for r in rep.requirements)


def test_every_text_names_its_writer_and_off_means_deterministic(out):
    rep = write(out)
    texts = [rep.executive_summary] + [r.plain_note for r in rep.requirements] + [r.explanation for r in rep.requirements]
    assert {t.writer for t in texts} == {"deterministic"}
    assert rep.provenance.slm_status == "off" and rep.provenance.slm is None and rep.provenance.sections_slm == 0
    md, html = to_markdown(rep), to_html(rep)
    assert md.count("written by: deterministic template") == 4 and "Written by: deterministic template" in md
    assert "Written by: deterministic template" in html


def test_disclaimer_and_no_verdict_words(out):
    rep = write(out)
    for doc in (to_markdown(rep), to_html(rep)):
        assert DISCLAIMER in doc.replace("&#x27;", "'")
        low = doc.lower().replace(DISCLAIMER.lower(), "")
        for w in ("recommend", "reject", "hire ", "suitable", "shortlist"):
            assert w not in low


def test_html_is_escaped_and_self_contained(out):
    html = to_html(write(out, job_title=JOB["title"]))
    assert "<script>" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<b>engineer</b>" not in html and "&lt;b&gt;engineer&lt;/b&gt;" in html
    assert "src=" not in html and "href=" not in html and "<link" not in html


def test_markdown_neutralises_markup(out):
    md = to_markdown(write(out, job_title=JOB["title"]))
    assert "<script>" not in md and "<b>" not in md


def test_mock_matcher_is_labelled(out):
    rep = write(out)
    assert rep.provenance.any_mock and all(r.model.mock for r in rep.requirements)
    assert "MOCK backend in the pipeline" in to_markdown(rep) and "MOCK backend in the pipeline" in to_html(rep)


def test_not_documented_note_is_absence_of_evidence(out):
    r3 = write(out).requirements[2]
    assert r3.decision == "MISSING" and "not proof of absence" in r3.plain_note.text


def test_write_files(out, tmp_path):
    write_files(out, tmp_path, job_title="x")
    assert {p.name for p in tmp_path.iterdir()} == {"report.report.json", "report.html", "report.slm.md"}


def test_judge_scores_bias_flip_and_backend_down_are_rendered(out):
    import copy

    o = copy.deepcopy(out)
    r1, r2 = o["requirements"][0], o["requirements"][1]
    r1["judge"] = {"judge_verdict": "FAIL", "judge_score": 0.123, "judge_disagrees": True, "requires_human_review": True,
                   "nli_probs": {"entailment": 0.1}, "premise_kind": "quote", "model": "nli-judge-pretrained", "error": None}
    r1["bias_audit"].update(audit_status="FLAGGED", counterfactual_flip=True, affected_attribute="name_signal")
    r2.update(final_decision="UNCERTAIN", basis="ambiguous", evidence=[], evidence_spans=[],
              review_reasons=["matcher:backend_unavailable"], requires_human_review=True)
    rep = write(o)
    assert rep.requirements[0].judge.verdict == "FAIL" and rep.requirements[0].judge.score == 0.123
    assert rep.requirements[1].plain_note.text.startswith("UNCERTAIN: no Matcher model answered")
    md, html = to_markdown(rep), to_html(rep)
    for doc in (md, html):
        assert "FAIL (score 0.123)" in doc and "counterfactual flip on name" in doc
