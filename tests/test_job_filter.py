"""Guardrail: sentences inside a requirement section that are not requirements (ANNOTATION_RULES.md §1)."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.job import FakeBackend, run_job_agent  # noqa: E402
from agents.job.validate import check_requirements, not_a_requirement  # noqa: E402

GOLD = sorted((ROOT / "eval/job_agent/gold").glob("*.json"))


# Real extra sentences kept by job-v4 on the 10 USAJOBS offers.
@pytest.mark.parametrize("sentence,kind", [
    ("Transcripts must be submitted to validate that the education requirement has been met.",
     "application instructions"),
    ("Your resume must include a clear and detailed narrative description, in your own words, of how you meet "
     "the required specialized experience.", "application instructions"),
    ("Click here to view a listing of accredited organizations from the Department of Education's website.",
     "application instructions"),
    ("U.S. degrees must have been awarded from colleges or universities that are accredited by recognized "
     "accrediting organizations.", "application instructions"),
    ("Education completed in foreign colleges or universities may be used to meet the requirements.",
     "application instructions"),
    ("Persons listed as knowing your past accomplishments or experience in your application may be contacted for "
     "verification purposes at any time.", "application instructions"),
    ("Experience refers to paid and unpaid experience, including volunteer work done through National Service "
     "programs (e.g., Peace Corps, AmeriCorps).", "definition"),
    ("One academic year of graduate education is the number of credits hours your graduate school has determined "
     "to represent one academic year of full-time study.", "definition"),
    ("Examples of such nonqualifying work include statistical clerical work; statistical drafting.", "definition"),
    ("For positions above the GS-05,applicants must meet applicable time-in-grade requirements to be considered "
     "eligible.", "administrative condition"),
    ("Continued employment is contingent upon satisfactorily completing a criminal history records check and a "
     "pre-employment drug-test (pre-identified position only).", "administrative condition"),
])
def test_non_requirement_text_is_recognised(sentence, kind):
    assert not_a_requirement(sentence) == kind


# Real requirements that contain a word close to a cue: the cues were narrowed for these.
@pytest.mark.parametrize("sentence", [
    "You must have successfully completed a full 4-year course of study in an accredited college or university "
    "leading to a bachelor's or higher degree.",
    "You must demonstrate in your resume at least one year (52 weeks) of qualifying specialized experience "
    "equivalent to the GS-14 grade level.",
    "Specialized experience is defined as: Extracting, aggregating, and cleaning complex data from relational "
    "databases.",
    "3 years of experience with Java and Spring Boot.",
    "Minimum 3 ans d'expérience avec Angular et Node.js.",
])
def test_real_requirements_pass(sentence):
    assert not_a_requirement(sentence) is None


def test_no_gold_quote_is_ever_filtered():
    """A cue that matches a gold requirement would silently lower recall."""
    hits = [(p.stem, r["evidence"][:80]) for p in GOLD
            for r in json.loads(p.read_text(encoding="utf-8"))["requirements"] if not_a_requirement(r["evidence"])]
    assert hits == []


def test_filtered_sentence_is_dropped_with_a_warning_but_not_counted_as_invented():
    post = "Requirements:\n- Experience with SQL.\n- Transcripts must be submitted with your application."
    items = [{"evidence": e, "skill_terms": [], "kind": "must", "category": "experience", "min_years": None,
              "text": e} for e in ("Experience with SQL.", "Transcripts must be submitted with your application.")]
    report = check_requirements(items, post)
    assert [r["evidence"] for r in report.requirements] == ["Experience with SQL."]
    assert (report.filtered, report.dropped) == (1, 0)
    assert any("not a requirement (application instructions)" in w for w in report.warnings)


def test_v4_does_not_ask_skill_names_for_a_filtered_sentence():
    post = ("Data Analyst\n\nRequirements:\n- Experience with SQL.\n"
            "- Transcripts must be submitted with your application.\n")
    sentences = [{"evidence": e, "skill_terms": [], "kind": "must", "category": "experience", "min_years": None,
                  "text": e} for e in ("Experience with SQL.", "Transcripts must be submitted with your application.")]

    def answer(text, template):
        if "job_title" in template:
            return json.dumps({"job_title": "Data Analyst"})
        if "requirements" not in template:  # the skill-names call
            return json.dumps({"skill_terms": ["SQL"] if "SQL" in text else []})
        return json.dumps({"requirements": [s for s in sentences if s["evidence"] in text]})

    fake = FakeBackend(answer)
    card = run_job_agent(post, "x", fake, prompt_version="job-v4")
    assert [(r.evidence, r.skill_terms) for r in card.requirements] == [("Experience with SQL.", ["SQL"])]
    assert not any("Transcripts" in c["text"] for c in fake.calls
                   if "skill_terms" in c["template"] and "requirements" not in c["template"])
    assert not card.needs_human_review
