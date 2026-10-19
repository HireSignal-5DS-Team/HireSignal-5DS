"""T15: Job Agent v2 / Profile Agent v2 prompts (no model)."""
import json
from pathlib import Path

import pytest

from services.job.prompts import get_prompt as job_prompt
from services.profile.parse import check_items, parse_cv
from services.profile.prompts import get_prompt as profile_prompt

ROOT = Path(__file__).resolve().parents[1]
DEV_SOURCES = [ROOT / "eval/job_agent/offers/usajobs-883337000.txt", ROOT / "eval/job_agent/offers/usajobs-883386100.txt",
               ROOT / "data/processed/jobs/J2.txt"]
TEST_SOURCES = sorted((ROOT / "eval/job_agent/offers").glob("usajobs-*.txt"))[5:] + [
    ROOT / "data/processed/jobs/J3.txt", ROOT / "data/processed/jobs/J4.txt"]


@pytest.mark.parametrize("version", ["job-v1", "job-v2"])
def test_job_prompt_files_load(version):
    system, examples = job_prompt(version)
    assert "JSON" in system and examples
    for ex in examples:
        out = json.loads(ex["output"])
        for r in out["requirements"]:
            assert r["evidence"] in ex["input"]  # every example quote is verbatim
            assert all(t in r["evidence"] for t in r["skill_terms"]), r  # terms are copied from the quote


def test_job_v2_few_shot_comes_from_dev_posts_only():
    _, examples = job_prompt("job-v2")
    dev = " ".join(" ".join(p.read_text(encoding="utf-8").split()) for p in DEV_SOURCES)
    test = " ".join(" ".join(p.read_text(encoding="utf-8").split()) for p in TEST_SOURCES)
    for ex in examples:
        for r in json.loads(ex["output"])["requirements"]:
            assert " ".join(r["evidence"].split()) in dev
            assert " ".join(r["evidence"].split()) not in test or len(r["evidence"]) < 25  # short names may recur


def test_job_v2_soft_attitude_example_is_nice():
    _, examples = job_prompt("job-v2")
    items = [r for ex in examples for r in json.loads(ex["output"])["requirements"]]
    assert any(r["evidence"].startswith("Wiliness") and r["kind"] == "nice" for r in items)


@pytest.mark.parametrize("version", ["profile-v1", "profile-v2"])
def test_profile_prompt_files_load(version):
    system, examples = profile_prompt(version)
    assert "evidence" in system and len(examples) == 2


def test_profile_v2_grouped_skills_give_the_same_items_as_v1():
    cv = "Section: SKILLS\nPython, SQL, Docker\nSpark"
    v1 = {"skills": [{"name": n, "evidence": "Python, SQL, Docker"} for n in ("Python", "SQL", "Docker")] +
          [{"name": "Spark", "evidence": "Spark"}], "education": [], "experience": []}
    v2 = {"skills": [{"names": ["Python", "SQL", "Docker"], "evidence": "Python, SQL, Docker"},
                     {"names": ["Spark"], "evidence": "Spark"}], "education": [], "experience": []}
    a, b = check_items(v1, cv, []), check_items(v2, cv, [])
    assert [s.model_dump() for s in a[0]] == [s.model_dump() for s in b[0]]
    assert [s.name for s in b[0]] == ["Python", "SQL", "Docker", "Spark"]


def test_profile_v2_group_with_an_invented_name_keeps_the_real_ones():
    cv = "Python, SQL"
    notes = []
    skills, _, _ = check_items({"skills": [{"names": ["Python", "Kubernetes"], "evidence": "Python, SQL"}]}, cv, notes)
    assert [s.name for s in skills] == ["Python"] and any("Kubernetes" in n for n in notes)


def test_parse_cv_with_v2_and_a_fake_backend():
    class Fake:
        def extract(self, text, template, examples):
            assert "GROUP BY LINE" in template
            return json.dumps({"skills": [{"names": ["Python", "Airflow"], "evidence": "Python and Airflow daily."}],
                               "education": [], "experience": []})

    prof = parse_cv("Python and Airflow daily.", "cv-00000000", Fake(), prompt_version="profile-v2")
    assert [s.name for s in prof.skills] == ["Python", "Airflow"] and prof.prompt_version == "profile-v2"


def test_grouped_name_from_another_line_is_reanchored_to_that_line():
    cv = "Backend developer.\nBuilt APIs with Django.\nPython daily."
    notes = []
    skills, _, _ = check_items({"skills": [{"names": ["Django", "Python"], "evidence": "Built APIs with Django."}]},
                               cv, notes)
    assert [(s.name, s.evidence) for s in skills] == [("Django", "Built APIs with Django."), ("Python", "Python daily.")]
    assert any("re-anchored" in n for n in notes)


def test_a_v1_item_is_never_reanchored():
    cv = "Built APIs with Django.\nPython daily."
    notes = []
    skills, _, _ = check_items({"skills": [{"name": "Python", "evidence": "Built APIs with Django."}]}, cv, notes)
    assert skills == [] and not any("re-anchored" in n for n in notes)


def test_a_punctuation_only_skill_name_is_dropped_not_a_crash():
    notes = []
    skills, _, _ = check_items({"skills": [{"names": [".", "SQL"], "evidence": "SQL."}]}, "SQL.", notes)
    assert [s.name for s in skills] == ["SQL"] and any("empty name" in n for n in notes)
