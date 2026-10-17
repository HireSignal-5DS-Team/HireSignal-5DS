"""Profile Agent step 4: anonymised text -> ParsedCV, with checks. Fake models, no GPU."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.job.backend import FakeBackend  # noqa: E402
from agents.profile import anonymise_cv, parse_cv, run_profile_agent  # noqa: E402
from agents.profile.parse import (check_items, chunk_sections, cv_sections, dates_in,  # noqa: E402
                                  normalise_date)
from agents.profile.prompts import EXAMPLES_P1, SYSTEM_P1  # noqa: E402
from agents.profile.scoring import score_skills  # noqa: E402
from contracts.profile import ParsedCV  # noqa: E402

EVAL = ROOT / "eval" / "profile_agent"

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
    assert parsed.candidate_id == "cv-x" and parsed.prompt_version == "profile-q1"


def test_the_model_only_sees_the_anonymised_text():
    text = (EVAL / "cvs/p01_en_classic.txt").read_text(encoding="utf-8")
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
        assert len(s) == len(data["skills"]) and len(e) == len(data["education"]) and len(x) == len(data["experience"])


def test_parsed_cv_has_no_identity_field():
    fields = set(ParsedCV.model_fields)
    assert not fields & {"name", "email", "phone", "photo", "age", "gender", "nationality", "address"}


def test_score_skills_alternatives_and_optional():
    s = score_skills(["CEH v11", "Python", "Incident response", "Blockchain"], [["CEH", "CEH v11"], ["Python"], ["SQL"]],
                     ["Incident response"])
    assert (s["tp"], s["fp"], s["fn"]) == (2, 1, 1) and s["missed"] == ["sql"] and s["extra"] == ["blockchain"]


# ------------------------------------------- perfect model on the 10 CVs ---

def _perfect(gold):
    """A fake model that answers exactly the gold, quoting the chunk's real lines."""
    def reply(chunk, template):
        lines = [l for l in chunk.splitlines() if l.strip() and not l.startswith("Section: ")]
        def line_with(value):
            return next((l for l in lines if value and value in l), None)
        skills = []
        for alts in gold["skills"]:
            for a in alts:
                if (l := line_with(a)):
                    skills.append({"name": a, "evidence": l})
                    break
        edu = [{**e, "evidence": l} for e in gold["education"] if (l := line_with(e["institution"] or e["degree"]))]
        exp = [{**x, "evidence": l} for x in gold["experience"] if (l := line_with(x["company"] or x["title"]))]
        return answer(skills=skills, education=edu, experience=exp)
    return reply


@pytest.mark.parametrize("gold_file", sorted((EVAL / "parse_gold").glob("*.json")), ids=lambda p: p.stem)
def test_checks_keep_every_correct_answer(gold_file):
    from agents.profile.scoring import score_parsed
    gold = json.loads(gold_file.read_text(encoding="utf-8"))
    text = (EVAL / "cvs" / f"{gold['cv']}.txt").read_text(encoding="utf-8")
    anon = anonymise_cv(text, cv_id=gold["cv"])
    parsed = parse_cv(anon.text, anon.cv_id, FakeBackend(_perfect(gold))).model_dump()
    scores = score_parsed(parsed, gold)
    for k in ("skills", "experience", "education"):
        assert scores[k]["f1"] == 1.0, (k, scores[k], parsed["uncertain"])
    for k in ("experience", "education"):
        assert scores[k]["field_errors"] == [], scores[k]["field_errors"]
