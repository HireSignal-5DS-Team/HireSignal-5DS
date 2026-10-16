"""Contract v1.1 (MOCK backends only): the real Pipeline output validates, and Ayoub's outputs adapt losslessly."""
import json
from pathlib import Path

from integration.contract import CONTRACT_VERSION, cv_from_reader, export, job_from_card, validate_output
from matcher.pipeline import Pipeline
from matcher.tests.test_agent_pipeline import CVX, ESCO, GOOD, JOB, Fake, judge_for

EX = Path(__file__).parents[1] / "examples"


def test_pipeline_output_matches_contract():
    out = Pipeline(Fake("lora", GOOD), ESCO, judge=judge_for(CVX.text)).run(CVX.model_dump(), JOB.model_dump())
    v = validate_output(out)
    assert v.contract_version == CONTRACT_VERSION and [r.req_id for r in v.requirements] == [r.req_id for r in JOB.requirements]
    for r in v.requirements:  # evidence stays traceable to the CV text
        assert all(CVX.text[a:b] == q for q, (a, b) in zip(r.evidence, r.evidence_spans))


def test_ayoub_reader_and_job_card_adapt():
    cv = cv_from_reader(json.loads((EX / "reader_result.json").read_text()), cv_id="cv-ex-1")
    job = job_from_card(json.loads((EX / "job_card.json").read_text()))
    assert cv.text.startswith("Software engineer") and cv.structured["reader"]["file_type"] == "pdf"
    assert [r.req_id for r in job.requirements] == ["r1", "r2", "r3"] and job.requirements[0].min_years == 3


def test_examples_are_valid_matcher_inputs():
    from matcher.schemas import CV, Job
    CV.model_validate_json((EX / "cv.json").read_text())
    Job.model_validate_json((EX / "job.json").read_text())


def test_schema_export(tmp_path):
    names = sorted(p.name for p in export(tmp_path).iterdir())
    assert names == ["CV.schema.json", "Job.schema.json", "PipelineOutput.schema.json"]
