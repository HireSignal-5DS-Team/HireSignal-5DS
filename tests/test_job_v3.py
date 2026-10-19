# Adapted from team V2: tests/test_job_v3.py (feature/agent-integration @ a5a03ff)
"""job-v3: requirement sections only, small chunks, salvage of cut-off answers."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.job import FakeBackend, JobAgentError, run_job_agent  # noqa: E402
from services.job.sections import CHUNK_CHARS, chunk_sections, heading_type, requirement_sections  # noqa: E402
from services.job.validate import parse_model_output, salvage_cut_json  # noqa: E402

FIELDS = ("evidence", "skill_terms", "kind", "category", "min_years", "text")
GOLD = sorted((ROOT / "tests/fixtures/job/gold").glob("*.json"))


def offer(job_id):
    return (ROOT / "tests/fixtures/job/offers" / f"{job_id}.txt").read_text(encoding="utf-8")


def oracle(gold_reqs, title="Job"):
    """A perfect fake model: for each chunk, the gold items whose quote is in that chunk."""
    def answer(text, template):
        if "job_title" in template:
            return json.dumps({"job_title": title})
        return json.dumps({"requirements": [{k: r[k] for k in FIELDS} for r in gold_reqs if r["evidence"] in text]})
    return answer


# ----------------------------------------------------------------- sections ---

@pytest.mark.parametrize("line,kind", [
    ("Qualifications", "requirement"), ("Requirements:", "requirement"), ("Profil recherché :", "requirement"),
    ("Nice to have:", "nice"), ("Preferred Qualifications", "nice"), ("Atouts", "nice"),
    ("Duties", "skip"), ("Conditions of employment", "skip"), ("Vos missions", "skip"),
    ("Experience with Python and SQL is required for this role.", None), ("", None),
])
def test_heading_type(line, kind):
    assert heading_type(line) == kind


def test_usajobs_offer_keeps_only_qualifications_and_education():
    sections = requirement_sections(offer("usajobs-883161100"))
    assert [s.heading for s in sections] == ["Qualifications", "Education"]
    assert "Must be a U.S. citizen" not in " ".join(s.text for s in sections)


def test_inline_additional_information_is_cut():
    text = "Qualifications\nOne year of experience with SQL. Additional information Relocation expenses paid."
    assert requirement_sections(text)[0].text == "One year of experience with SQL."


def test_chunks_are_small_and_keep_every_word():
    sections = requirement_sections(offer("usajobs-883699600"))
    chunks = chunk_sections(sections)
    assert all(len(c) <= CHUNK_CHARS + 200 for c, _ in chunks)
    assert " ".join(" ".join(c.split()) for c, _ in chunks) == " ".join(" ".join(s.text.split()) for s in sections)


def test_gold_quotes_are_all_inside_the_chunks():
    """The section filter must never hide a real requirement from the model."""
    for path in GOLD:
        gold = json.loads(path.read_text(encoding="utf-8"))
        chunks = [c for c, _ in chunk_sections(requirement_sections(offer(gold["job_id"])))]
        for r in gold["requirements"]:
            assert any(r["evidence"] in c for c in chunks), (gold["job_id"], r["req_id"])


# ------------------------------------------------------------- v3 end to end ---

@pytest.mark.parametrize("path", GOLD, ids=lambda p: p.stem)
def test_v3_with_a_perfect_model_gives_back_the_gold(path):
    gold = json.loads(path.read_text(encoding="utf-8"))
    card = run_job_agent(offer(gold["job_id"]), gold["job_id"], FakeBackend(oracle(gold["requirements"])))
    got = sorted((r.evidence, tuple(r.skill_terms), r.kind, r.category, r.min_years) for r in card.requirements)
    want = sorted((r["evidence"], tuple(r["skill_terms"]), r["kind"], r["category"], r["min_years"])
                  for r in gold["requirements"])
    assert got == want, card.warnings


def test_v3_sends_only_small_chunks_and_never_the_conditions():
    fake = FakeBackend(oracle([]))
    with pytest.raises(JobAgentError):  # a model that finds nothing: no requirement survives
        run_job_agent(offer("usajobs-883827900"), "x", fake)
    chunk_calls = [c for c in fake.calls if "job_title" not in c["template"]]
    assert len(chunk_calls) > 1
    assert not any("Selective Service" in c["text"] for c in chunk_calls)


def test_v3_nice_section_makes_items_nice():
    post = "Data Analyst\n\nRequirements:\n- Experience with SQL.\n\nNice to have:\n- Experience with Tableau."
    items = [{"evidence": "Experience with SQL.", "skill_terms": ["SQL"], "kind": "must", "category": "experience",
              "min_years": None, "text": "SQL"},
             {"evidence": "Experience with Tableau.", "skill_terms": ["Tableau"], "kind": "must",
              "category": "experience", "min_years": None, "text": "Tableau"}]
    card = run_job_agent(post, "x", FakeBackend(oracle(items, "Data Analyst")))
    assert [(r.skill_terms, r.kind) for r in card.requirements] == [(["SQL"], "must"), (["Tableau"], "nice")]
    assert card.title == "Data Analyst"


def test_v3_offer_without_headings_uses_the_whole_text():
    post = "We hire a developer. You need 2 years of experience with Go. Remote work possible."
    items = [{"evidence": "You need 2 years of experience with Go.", "skill_terms": ["Go"], "kind": "must",
              "category": "experience", "min_years": 2, "text": "2 years of Go"}]
    card = run_job_agent(post, "x", FakeBackend(oracle(items)))
    assert len(card.requirements) == 1
    assert any("no requirement section" in w for w in card.warnings)


def test_v3_one_broken_chunk_does_not_lose_the_card():
    post = offer("usajobs-883699600")
    gold = json.loads((ROOT / "tests/fixtures/job/gold/usajobs-883699600.json").read_text(encoding="utf-8"))
    good = oracle(gold["requirements"])
    state = {"n": 0}

    def flaky(text, template):
        state["n"] += 1
        return "garbage" if state["n"] in (1, 2) else good(text, template)  # chunk 1 fails twice

    card = run_job_agent(post, "x", FakeBackend(flaky))
    assert 0 < len(card.requirements) < len(gold["requirements"])
    assert card.needs_human_review
    assert any("chunks gave no usable answer" in w for w in card.warnings)


# --------------------------------------------------------- cut-off answers (E1) ---

def test_cut_off_answer_keeps_the_complete_items():
    """Real evaluation: 5 of 20 answers stopped mid-sentence at the token limit."""
    cut = ('{"title": "X", "requirements": [{"evidence": "A.", "kind": "must"}, '
           '{"evidence": "B.", "kind": "nice"}, {"evidence": "half a sent')
    data, kept = salvage_cut_json(cut)
    assert kept == 2 and [r["evidence"] for r in data["requirements"]] == ["A.", "B."]
    assert parse_model_output(cut)["_salvaged"] == 2


def test_nothing_to_salvage_still_raises():
    with pytest.raises(ValueError):
        parse_model_output('{"requirements": [{"evidence": "half')


def test_salvaged_answer_is_reported_in_the_card():
    post = (ROOT / "tests/fixtures/job/job_post.example.txt").read_text(encoding="utf-8")
    cut = ('{"title": "Backend Developer", "requirements": [{"evidence": "Fluent French", "skill_terms": ["French"], '
           '"kind": "must", "category": "language", "min_years": null, "text": "Fluent French"}, {"evidence": "AWS cert')
    # V2 ran this on the whole-offer path (job-v2); ours is sections only: the cut answer comes for the chunk
    # holding the quote, the title call and other chunks get normal answers.
    def reply(text, template):
        if "job_title" in template:
            return '{"job_title": "Backend Developer"}'
        return cut if "Fluent French" in text else '{"requirements": []}'
    card = run_job_agent(post, "x", FakeBackend(reply))
    assert len(card.requirements) == 1
    assert any("cut off" in w for w in card.warnings)
