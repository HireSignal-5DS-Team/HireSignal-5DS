# Adapted from team V2: tests/test_job_contract.py (feature/agent-integration @ a5a03ff)
"""The Job Agent's output contract (contracts/job_requirements.py)."""

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.job.contracts import JobRequirements  # noqa: E402

EXAMPLE = json.loads((ROOT / "tests/fixtures/job/job_requirements.example.json").read_text(encoding="utf-8"))
JOB_POST = (ROOT / "tests/fixtures/job/job_post.example.txt").read_text(encoding="utf-8")


def test_example_is_valid():
    card = JobRequirements.model_validate(EXAMPLE)
    assert len(card.requirements) == 9


def test_every_evidence_is_an_exact_quote_from_the_job_post():
    card = JobRequirements.model_validate(EXAMPLE)
    for r in card.requirements:
        assert r.evidence in JOB_POST, f"{r.req_id}: evidence not found in job post"


def test_converts_to_matcher_job_format():
    job = JobRequirements.model_validate(EXAMPLE).to_matcher_job()
    assert set(job) == {"job_id", "title", "requirements"}
    assert set(job["requirements"][0]) == {"req_id", "text", "kind", "category", "skill_terms", "min_years"}
    assert job["requirements"][0]["min_years"] == 3


def _with(**changes):
    data = json.loads(json.dumps(EXAMPLE))
    data["requirements"][0].update(changes)
    return data


@pytest.mark.parametrize("bad", [
    {"kind": "required"},          # only must / nice
    {"category": "soft skill"},    # unknown category
    {"req_id": "R-1"},             # ids are r1, r2, ...
    {"evidence": ""},              # a quote is mandatory
    {"min_years": -1},
    {"salary": "2000 TND"},        # no extra fields
])
def test_invalid_requirements_are_refused(bad):
    with pytest.raises(ValidationError):
        JobRequirements.model_validate(_with(**bad))


def test_duplicate_ids_are_refused():
    data = json.loads(json.dumps(EXAMPLE))
    data["requirements"][1]["req_id"] = "r1"
    with pytest.raises(ValidationError, match="duplicate req_id"):
        JobRequirements.model_validate(data)


def test_empty_requirement_list_is_refused():
    data = json.loads(json.dumps(EXAMPLE))
    data["requirements"] = []
    with pytest.raises(ValidationError):
        JobRequirements.model_validate(data)


def test_exported_json_schema_is_up_to_date():
    exported = json.loads((ROOT / "services/job/job_requirements.schema.json").read_text(encoding="utf-8"))
    assert exported["models"]["JobRequirements"] == JobRequirements.model_json_schema(), \
        "run: python -m services.job.contracts"
