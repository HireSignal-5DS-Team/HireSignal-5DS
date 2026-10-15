"""Job Agent tests, with a fake NuExtract (no model or GPU needed)."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.job import FakeBackend, JobAgentError, run_job_agent  # noqa: E402
from agents.job import prompts  # noqa: E402
from agents.job.backend import NuExtractClient, build_inline_prompt  # noqa: E402
from agents.job.validate import locate_evidence, years_in  # noqa: E402
from contracts.job_requirements import JobRequirements  # noqa: E402

POST = (ROOT / "examples/job_post.example.txt").read_text(encoding="utf-8")
GOLD = json.loads((ROOT / "examples/job_requirements.example.json").read_text(encoding="utf-8"))


def answer(requirements, title="Backend Developer"):
    """A NuExtract-style answer (what the model returns)."""
    return json.dumps({"title": title, "requirements": requirements})


def req(text, evidence, kind="must", category="skill", skill_terms=(), min_years=None):
    return {"text": text, "evidence": evidence, "kind": kind, "category": category,
            "skill_terms": list(skill_terms), "min_years": min_years}


PERFECT = answer([{k: v for k, v in r.items() if k not in ("req_id", "chunk_ids")}
                  for r in GOLD["requirements"]])


# ------------------------------------------------------------ happy path ---

def test_perfect_answer_gives_the_expected_card():
    card = run_job_agent(POST, "JD-001", FakeBackend([PERFECT]))
    assert isinstance(card, JobRequirements)
    assert [r.req_id for r in card.requirements] == [f"r{i}" for i in range(1, 9)]
    assert card.to_matcher_job()["requirements"] == JobRequirements.model_validate(GOLD).to_matcher_job()["requirements"]
    assert card.warnings == [] and not card.needs_human_review
    assert card.language == "en" and card.title == "Backend Developer"


def test_template_and_examples_are_sent_to_the_model():
    fake = FakeBackend([PERFECT])
    run_job_agent(POST, "JD-001", fake)
    call = fake.calls[0]
    assert '"evidence": "verbatim-string"' in call["template"]
    assert len(call["examples"]) == 2


def test_prompt_examples_obey_their_own_rules():
    """Every quote in the few-shot examples must be in its example input."""
    for ex in prompts.EXAMPLES:
        out = json.loads(ex["output"])
        for r in out["requirements"]:
            assert r["evidence"] in ex["input"], r["evidence"]


# --------------------------------------------------------------- guardrails ---

def test_invented_requirement_is_dropped():
    fake = FakeBackend([answer([
        req("Java", "At least 3 years of professional experience with Java and Spring Boot.",
            category="experience", skill_terms=["Java"], min_years=3),
        req("Kubernetes required", "5 years of Kubernetes in production is required.",
            skill_terms=["Kubernetes"], min_years=5),
    ])])
    card = run_job_agent(POST, "JD-001", fake)
    assert [r.text for r in card.requirements] == ["Java"]
    assert any("invented" in w for w in card.warnings)
    assert card.needs_human_review  # 1 of 2 proposals invented


def test_quote_with_different_spacing_is_mapped_back_to_the_real_text():
    sloppy = "at least 3 years  of professional\nexperience with Java and Spring Boot."
    card = run_job_agent(POST, "JD-001", FakeBackend([answer([
        req("Java", sloppy, category="experience", skill_terms=["Java"], min_years=3)])]))
    assert card.requirements[0].evidence == \
        "At least 3 years of professional experience with Java and Spring Boot."


def test_small_copy_slip_is_repaired():
    slip = "Solid knowledge of SQL databses (PostgreSQL or Oracle)"
    card = run_job_agent(POST, "JD-001", FakeBackend([answer([req("SQL", slip, skill_terms=["SQL"])])]))
    assert card.requirements[0].evidence == "Solid knowledge of SQL databases (PostgreSQL or Oracle)."
    assert any("fuzzy" in w for w in card.warnings)


def test_wrong_years_are_corrected_from_the_quote():
    card = run_job_agent(POST, "JD-001", FakeBackend([answer([
        req("Java", "At least 3 years of professional experience with Java and Spring Boot.",
            category="experience", skill_terms=["Java"], min_years=5)])]))
    assert card.requirements[0].min_years == 3


def test_years_without_a_number_in_the_quote_are_removed():
    card = run_job_agent(POST, "JD-001", FakeBackend([answer([
        req("SQL", "Solid knowledge of SQL databases (PostgreSQL or Oracle).", skill_terms=["SQL"], min_years=2)])]))
    assert card.requirements[0].min_years is None


def test_optional_wording_forces_nice():
    card = run_job_agent(POST, "JD-001", FakeBackend([answer([
        req("Docker", "Experience with Docker and Kubernetes is a plus.", kind="must", skill_terms=["Docker"])])]))
    assert card.requirements[0].kind == "nice"


def test_skill_terms_not_in_the_quote_are_removed():
    card = run_job_agent(POST, "JD-001", FakeBackend([answer([
        req("SQL", "Solid knowledge of SQL databases (PostgreSQL or Oracle).", skill_terms=["SQL", "MongoDB"])])]))
    assert card.requirements[0].skill_terms == ["SQL"]


def test_duplicates_are_dropped():
    item = req("SQL", "Solid knowledge of SQL databases (PostgreSQL or Oracle).", skill_terms=["SQL"])
    card = run_job_agent(POST, "JD-001", FakeBackend([answer([item, item])]))
    assert len(card.requirements) == 1


def test_unknown_category_becomes_other():
    card = run_job_agent(POST, "JD-001", FakeBackend([answer([
        req("SQL", "Solid knowledge of SQL databases (PostgreSQL or Oracle).", category="hard skill")])]))
    assert card.requirements[0].category == "other"


# ------------------------------------------------------------- retry loop ---

def test_unreadable_answer_is_retried_once():
    fake = FakeBackend(["Sorry, I cannot do that", PERFECT])
    card = run_job_agent(POST, "JD-001", fake)
    assert len(fake.calls) == 2 and len(card.requirements) == 8
    assert any("unreadable" in w for w in card.warnings)


def test_json_wrapped_in_code_fence_is_accepted():
    card = run_job_agent(POST, "JD-001", FakeBackend(["```json\n" + PERFECT + "\n```"]))
    assert len(card.requirements) == 8


def test_two_unreadable_answers_raise():
    with pytest.raises(JobAgentError, match="valid JSON"):
        run_job_agent(POST, "JD-001", FakeBackend(["nope", "still nope"]))


def test_everything_invented_raises():
    with pytest.raises(JobAgentError, match="No requirement survived"):
        run_job_agent(POST, "JD-001", FakeBackend([answer([req("Rust", "10 years of Rust.")])]))


def test_too_short_job_offer_raises():
    with pytest.raises(JobAgentError):
        run_job_agent("Hiring!", "JD-002", FakeBackend([PERFECT]))


def test_title_not_in_post_falls_back_to_first_line():
    card = run_job_agent(POST, "JD-001", FakeBackend([PERFECT.replace("Backend Developer", "Senior Wizard", 1)]))
    assert card.title.startswith("Backend Developer")


# ------------------------------------------------------------- French post ---

FR_POST = """Ingénieur DevOps - Tunis

Profil :
- Au moins deux ans d'expérience avec Kubernetes.
- Maîtrise de Linux.
- Une certification AWS serait un atout."""


def test_french_offer():
    card = run_job_agent(FR_POST, "JD-FR", FakeBackend([answer([
        req("Kubernetes", "Au moins deux ans d'expérience avec Kubernetes.", category="experience",
            skill_terms=["Kubernetes"]),
        req("Linux", "Maîtrise de Linux.", skill_terms=["Linux"]),
        req("Certification AWS", "Une certification AWS serait un atout.", kind="must",
            category="certification", skill_terms=["AWS"]),
    ], title="Ingénieur DevOps")]))
    assert card.language == "fr"
    assert card.requirements[0].min_years == 2      # "deux ans" filled in from the quote
    assert card.requirements[2].kind == "nice"      # "serait un atout"


# ------------------------------------------------------------- helpers ---

@pytest.mark.parametrize("text,expected", [
    ("3+ years of Java", [3]), ("Minimum 5 ans", [5]), ("two years", [2]),
    ("3-5 years", [3]), ("often years later", []), ("Fluent French", []),
])
def test_years_in(text, expected):
    assert years_in(text) == expected


def test_locate_evidence_rejects_unrelated_text():
    found, how = locate_evidence("Ten years of COBOL on mainframes.", POST)
    assert found is None and how.startswith("not found")


def test_inline_prompt_layout():
    prompt = build_inline_prompt("JOB TEXT", '{"a": "string"}', [{"input": "IN", "output": "OUT"}])
    assert prompt.index("# Template:") < prompt.index("# Examples:") < prompt.index("# Context:")
    assert prompt.endswith("JOB TEXT")


def test_kwargs_mode_sends_template_the_official_way():
    payload = NuExtractClient(base_url="http://x/v1", mode="kwargs")._payload("TXT", "{}", [])
    assert payload["chat_template_kwargs"] == {"template": "{}", "examples": []}
    assert payload["temperature"] == 0
