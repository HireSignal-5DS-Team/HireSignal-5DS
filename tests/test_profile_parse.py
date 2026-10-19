# Adapted from team V2: tests/test_profile_parse.py (feature/agent-integration @ a5a03ff)
"""Profile Agent step 4: anonymised text -> ParsedCV, with checks. Fake models, no GPU."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.job.backend import FakeBackend  # noqa: E402
from services.profile import anonymise_cv, parse_cv, run_profile_agent  # noqa: E402
from services.profile.parse import (_expand_skill_groups, check_items, chunk_sections, cv_sections, dates_in,  # noqa: E402
                                  normalise_date)
from services.profile.prompts import PROMPT_VERSION, get_prompt  # noqa: E402
from services.profile.contracts import ParsedCV  # noqa: E402

SYSTEM_P1, EXAMPLES_P1 = get_prompt()  # the production version (T15: prompts/profile/v3.md)

ANON = """[NAME] | Data Scientist
[EMAIL] • [PHONE]

SUMMARY
Data scientist with 3 years of experience in Python.

EXPERIENCE
Data Scientist, Vermeg — Tunis    2021 - 2024
- Churn models with XGBoost and scikit-learn.
Data Analyst Intern, Sofrecom    06/2020 - 09/2020

EDUCATION
Engineering degree in Computer Science, ESPRIT, 2021

SKILLS
Python, SQL, Docker

REFERENCES
[NAME], ESPRIT, [EMAIL]
"""


def answer(**lists):
    return json.dumps({"skills": [], "education": [], "experience": [], **lists})


# ----------------------------------------------------------------- dates ---

@pytest.mark.parametrize("raw,want", [
    ("2021", "2021"), ("06/2020", "2020-06"), ("2020-06", "2020-06"), ("mars 2019", "2019-03"),
    ("Sept. 2020", "2020-09"), ("juin 2020", "2020-06"), ("juillet 2021", "2021-07"), ("present", "present"),
    ("Present", "present"), ("depuis 2022", "present"), ("Aujourd'hui", "present"), ("now", "present"),
    ("summer 2021", "2021"), (None, None), ("n/a", None), ("13/2020", "2020"),
])
def test_normalise_date(raw, want):
    assert normalise_date(raw) == want


def test_start_dates_are_never_present():
    assert normalise_date("depuis 2022", allow_present=False) == "2022"


def test_dates_in_a_line():
    assert dates_in("Telnet, Tunis (2020 – 2024)") == ["2020", "2024"]
    assert dates_in("06/2020 - 09/2020") == ["2020-06", "2020-09"]
    assert dates_in("InstaDeep 2022 - present") == ["2022", "present"]


# -------------------------------------------------------------- sections ---

def test_sections_skip_header_contact_and_references():
    names = [h for h, _ in cv_sections(ANON)]
    assert names == ["SUMMARY", "EXPERIENCE", "EDUCATION", "SKILLS"]


def test_no_heading_means_whole_text():
    assert cv_sections("Python developer, 5 years at Vermeg\n") == [("CV", "Python developer, 5 years at Vermeg\n")]


def test_chunks_group_sections_and_cut_long_ones():
    chunks = chunk_sections(cv_sections(ANON))
    assert len(chunks) == 1 and chunks[0].startswith("Section: SUMMARY")
    long = [("EXPERIENCE", "\n".join(f"- line {i} " + "x" * 80 for i in range(60)))]
    parts = chunk_sections(long, 1500)
    assert len(parts) > 1 and all(p.startswith("Section: EXPERIENCE") and len(p) <= 1600 for p in parts)


# ---------------------------------------------------------------- checks ---

def test_good_items_pass_and_dates_are_normalised():
    notes = []
    skills, edu, exp = check_items(json.loads(answer(
        skills=[{"name": "XGBoost", "evidence": "- Churn models with XGBoost and scikit-learn."}],
        education=[{"degree": "Engineering degree", "field": "Computer Science", "institution": "ESPRIT",
                    "end": "2021", "evidence": "Engineering degree in Computer Science, ESPRIT, 2021"}],
        experience=[{"title": "Data Analyst Intern", "company": "Sofrecom", "start": "06/2020", "end": "09/2020",
                     "evidence": "Data Analyst Intern, Sofrecom    06/2020 - 09/2020"}])), ANON, notes)
    assert [s.name for s in skills] == ["XGBoost"]
    assert (edu[0].institution, edu[0].end) == ("ESPRIT", "2021")
    assert (exp[0].start, exp[0].end) == ("2020-06", "2020-09")
    assert notes == []


def test_invented_evidence_is_dropped():
    notes = []
    skills, _, exp = check_items(json.loads(answer(
        skills=[{"name": "Kubernetes", "evidence": "Deployed on Kubernetes clusters."}],
        experience=[{"title": "CTO", "company": "Google", "start": "2019", "end": "2024",
                     "evidence": "CTO, Google 2019 - 2024"}])), ANON, notes)
    assert skills == [] and exp == [] and len(notes) == 2


def test_value_not_in_its_evidence_is_removed():
    notes = []
    _, _, exp = check_items(json.loads(answer(experience=[
        {"title": "Senior Data Scientist", "company": "Vermeg", "start": "2019", "end": "2024",
         "evidence": "Data Scientist, Vermeg — Tunis    2021 - 2024"}])), ANON, notes)
    assert exp[0].title is None and exp[0].company == "Vermeg"          # "Senior" was invented
    assert exp[0].start is None and exp[0].end == "2024"                 # 2019 is not in the line
    assert len(notes) == 2


def test_placeholders_never_become_values():
    notes = []
    skills, edu, _ = check_items(json.loads(answer(
        skills=[{"name": "[NAME]", "evidence": "[NAME], ESPRIT, [EMAIL]"}],
        education=[{"degree": None, "field": None, "institution": "[NAME]", "end": None,
                    "evidence": "[NAME], ESPRIT, [EMAIL]"}])), ANON, notes)
    assert skills == [] and edu == []


def test_a_range_given_as_start_is_split():
    _, _, exp = check_items(json.loads(answer(experience=[
        {"title": "Data Scientist", "company": "Vermeg", "start": "2021 - 2024", "end": None,
         "evidence": "Data Scientist, Vermeg — Tunis    2021 - 2024"}])), ANON, [])
    assert (exp[0].start, exp[0].end) == ("2021", "2024")


def test_missing_dates_are_taken_from_the_evidence():
    notes = []
    _, _, exp = check_items(json.loads(answer(experience=[
        {"title": "Data Scientist", "company": "Vermeg", "evidence": "Data Scientist, Vermeg — Tunis    2021 - 2024"}])),
        ANON, notes)
    assert (exp[0].start, exp[0].end) == ("2021", "2024") and "dates taken from the evidence" in notes[0]


def test_present_needs_a_present_word():
    _, _, exp = check_items(json.loads(answer(experience=[
        {"title": "Data Scientist", "company": "Vermeg", "start": "2021", "end": "present",
         "evidence": "Data Scientist, Vermeg — Tunis    2021 - 2024"}])), ANON, [])
    assert exp[0].end is None


def test_not_a_list_is_ignored():
    notes = []
    assert check_items({"skills": "Python, SQL"}, ANON, notes) == ([], [], [])
    assert "not a list" in notes[0]


# ----------------------------------------------------------------- agent ---

def test_parse_cv_retries_unreadable_and_merges_duplicates():
    good = answer(skills=[{"name": "Python", "evidence": "Data scientist with 3 years of experience in Python."},
                          {"name": "python", "evidence": "Python, SQL, Docker"}])
    backend = FakeBackend(["sorry, here it is:", good])
    parsed = parse_cv(ANON, "cv-x", backend)
    assert [s.name for s in parsed.skills] == ["Python"]
    assert any("unreadable" in n for n in parsed.uncertain)
    assert parsed.candidate_id == "cv-x" and parsed.prompt_version == PROMPT_VERSION


def test_the_model_only_sees_the_anonymised_text():
    from test_profile_privacy import CV as text  # V2 read eval/profile_agent/cvs/p01_en_classic.txt (not copied)
    backend = FakeBackend(lambda chunk, template: answer())
    result = run_profile_agent(text, cv_id="cv-x", backend=backend)
    sent = json.dumps([c["text"] for c in backend.calls])
    for secret in ("JOHN", "Smith", "john.smith92", "345 678", "Tunisian", "1999", "Leila", "Haddad"):
        assert secret not in sent, secret
    assert backend.calls and backend.calls[0]["template"] == SYSTEM_P1 and backend.calls[0]["examples"] == EXAMPLES_P1
    assert "profile" in result.to_matcher_cv()["structured"]


def test_without_a_model_step_4_is_skipped():
    result = run_profile_agent(ANON.replace("[NAME]", "John Smith"), cv_id="cv-x")
    assert result.profile is None and "profile" not in result.to_matcher_cv()["structured"]


def test_examples_follow_their_own_rules():
    """Every example answer passes the checks on its own input (no invented evidence)."""
    for ex in EXAMPLES_P1:
        notes = []
        data = json.loads(ex["output"])
        s, e, x = check_items(data, ex["input"], notes)
        assert notes == [], notes
        assert len(s) == len(_expand_skill_groups(data["skills"])) and len(e) == len(data["education"]) and len(x) == len(data["experience"])


def test_parsed_cv_has_no_identity_field():
    fields = set(ParsedCV.model_fields)
    assert not fields & {"name", "email", "phone", "photo", "age", "gender", "nationality", "address"}


# Not ported (T04): score_skills and the "perfect model on the 10 CVs" tests read V2's eval/profile_agent/ files
# and agents/profile/scoring.py (evaluation code, not copied).


# ------------------------------------------------- T08b: text before the first heading ---

P45_LIKE = ("Position: Data Architect\nExperience years: 11\n\nExperienced data engineer / data architect / system "
            "analyst.\n\nLatest projects:\n- Migration from Vertica to Snowflake\n- Data Warehouse for an investment "
            "bank with 100+ data sources\n- Analytical system for a fund management company\n\nInterests:\nchess, hiking")


def test_text_before_the_only_skipped_heading_is_parsed():
    """P45 (T08): the only heading was 'Interests' (skipped) and V2 dropped the text before it: nothing parsed."""
    sections = cv_sections(P45_LIKE)
    assert sections and sections[0][0] == "CV" and "Snowflake" in sections[0][1]
    backend = FakeBackend(lambda chunk, template: answer(skills=[{"name": "Snowflake",
                                                                  "evidence": "- Migration from Vertica to Snowflake"}]))
    parsed = parse_cv(P45_LIKE, "cv-x", backend)
    assert backend.calls and [s.name for s in parsed.skills] == ["Snowflake"]


def test_a_short_header_before_the_first_heading_is_still_skipped():
    names = [h for h, _ in cv_sections(ANON)]
    assert names == ["SUMMARY", "EXPERIENCE", "EDUCATION", "SKILLS"]  # [NAME] / [EMAIL] header lines stay out
