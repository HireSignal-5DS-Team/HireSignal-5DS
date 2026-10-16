"""Term-scoped years (validator v2). QA-031: a duration stated in another clause of the skill's own sentence counts."""
from matcher.validate import evidence_years as ey


def test_duration_in_sibling_clause_of_same_sentence():  # QA-031 (held-out test phrasing)
    assert ey(["Over the last 6 years, Airflow was the main tool at work."], terms=["Airflow"]) == 6


def test_other_skill_years_still_do_not_count():  # QA-004
    assert ey(["2 years of Python, 10 years of Java"], terms=["Python"]) == 2
    assert ey(["2 years of Python, 10 years of Java"], terms=["Java"]) == 10


def test_no_stated_duration_stays_unverified():  # QA-026
    assert ey(["Built side projects with React over time"], terms=["React"]) is None
