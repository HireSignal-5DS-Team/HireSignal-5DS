"""Held-out-style phrasing variants for duration evidence (QA-031 lesson). MOCK: scripted MET answers replayed through
the current validator. Written from general CV phrasing knowledge, WITHOUT reading benchmark/data/test.jsonl.

Requirement: Python, at least 5 years. A verbatim quote that states >= 5 years of Python must stay MET without a
duration flag; one that states fewer years of Python (or years of another skill only) must not stay an unflagged MET.
"""
import pytest
from _qa_support import check, defect, req

from matcher import CV

PY5 = req("r1", "At least 5 years of Python", category="experience", skill_terms=["Python"], min_years=5)

ENOUGH = [  # (quote) every one states >= 5 years of Python
    "Over the last 6 years, Python was the main tool at work.",          # duration before the skill (QA-031)
    "For 7 years I have worked daily with Python.",
    "Python, used daily for the past 5 years.",                           # duration in a sibling clause after
    "Python (6 years) in production systems.",                            # parentheses
    "Python developer - 8 years.",
    "Python | 6 yrs",
    "5+ years: Python, Django and FastAPI.",
    "Worked with Python from 2016 to 2023.",
    "Python: 2017 - 2024",
    "In 2015-2021 I built Python services for logistics.",
    "Python experience: 2019 - present.",
]
ENOUGH_UNPARSED = [  # true MET, but the duration is written in a form the parser does not read today
    "Since 2018, Python has been my main language.",
    "Seven years of Python in production.",
    "Python since 2019.",
]
NOT_ENOUGH = [
    "2 years of Python, 10 years of Java.",          # years of another skill (QA-004)
    "Over the last 3 years, Python was the main tool at work.",
    "Python (2 years) in side projects.",
    "Worked with Python from 2021 to 2023.",
]


def _met(quote):
    return check("MET", "supported", [quote], CV(cv_id="d", text=f"- {quote}"), PY5)


@pytest.mark.parametrize("quote", ENOUGH)
def test_duration_variant_is_read(quote):
    r = _met(quote)
    assert r.decision == "MET", (quote, r.review_reasons)
    assert not {"duration_not_verified", "years_below_minimum_in_evidence"} & set(r.review_reasons)


@pytest.mark.parametrize("quote", NOT_ENOUGH)
def test_insufficient_duration_is_not_an_unflagged_met(quote):
    r = _met(quote)
    assert r.decision != "MET" or r.needs_human_review, (quote, r.review_reasons)


@defect("QA-032", "S6")
@pytest.mark.parametrize("quote", ENOUGH_UNPARSED)
def test_unparsed_duration_forms(quote):
    r = _met(quote)
    assert r.decision == "MET", (quote, r.review_reasons)
