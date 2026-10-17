"""job-v4: job-v3 plus a second call per requirement sentence that only asks for the skill names."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.job import FakeBackend, run_job_agent  # noqa: E402

GOLD = sorted((ROOT / "eval/job_agent/gold").glob("*.json"))


def offer(job_id):
    return (ROOT / "eval/job_agent/offers" / f"{job_id}.txt").read_text(encoding="utf-8")


def is_terms_call(template):
    return "skill_terms" in template and "requirements" not in template


def model(sentences, terms, title="Job"):
    """Fake NuExtract. sentences: items the first call finds (with empty skill_terms, like the
    real model); terms: sentence -> skill names answered by the terms call."""
    def answer(text, template):
        if "job_title" in template:
            return json.dumps({"job_title": title})
        if is_terms_call(template):
            return json.dumps({"skill_terms": terms.get(text, [])})
        return json.dumps({"requirements": [s for s in sentences if s["evidence"] in text]})
    return answer


def item(evidence, kind="must", category="experience", years=None, terms=()):
    return {"evidence": evidence, "skill_terms": list(terms), "kind": kind, "category": category,
            "min_years": years, "text": evidence.rstrip(".")}


POST = ("Backend Developer\n\nRequirements:\n"
        "- 3 years of experience with Java and Spring Boot.\n"
        "- Experience with PostgreSQL or Oracle.\n"
        "- Bachelor's degree in computer science.\n")


def test_v4_terms_make_compound_lines_split():
    sentences = [item("3 years of experience with Java and Spring Boot.", years=3),
                 item("Experience with PostgreSQL or Oracle."),
                 item("Bachelor's degree in computer science.", category="education")]
    terms = {"3 years of experience with Java and Spring Boot.": ["Java", "Spring Boot"],
             "Experience with PostgreSQL or Oracle.": ["PostgreSQL", "Oracle"]}
    card = run_job_agent(POST, "x", FakeBackend(model(sentences, terms)), prompt_version="job-v4")
    assert [(r.text, r.skill_terms, r.min_years) for r in card.requirements] == [
        ("3 years of experience with Java", ["Java"], 3),
        ("3 years of experience with Spring Boot", ["Spring Boot"], 3),
        ("Experience with PostgreSQL or Oracle", ["PostgreSQL", "Oracle"], None),
        ("Bachelor's degree in computer science", [], None),
    ]


def test_v4_asks_once_per_sentence_with_the_real_text():
    # The first call quotes the same line twice (two chunks), once with a case slip.
    sentences = [item("3 years of experience with Java and Spring Boot.", years=3),
                 item("3 years of experience with java and Spring Boot.", years=3)]
    fake = FakeBackend(lambda text, template: (
        json.dumps({"requirements": sentences}) if "requirements" in template
        else model([], {"3 years of experience with Java and Spring Boot.": ["Java"]})(text, template)))
    run_job_agent(POST, "x", fake, prompt_version="job-v4")
    asked = [c["text"] for c in fake.calls if is_terms_call(c["template"])]
    assert asked == ["3 years of experience with Java and Spring Boot."]


def test_v4_keeps_model_terms_and_removes_terms_not_in_the_quote():
    sentences = [item("Experience with PostgreSQL or Oracle.", terms=["PostgreSQL"])]
    terms = {"Experience with PostgreSQL or Oracle.": ["postgresql", "Oracle", "MongoDB"]}
    card = run_job_agent(POST, "x", FakeBackend(model(sentences, terms)), prompt_version="job-v4")
    assert card.requirements[0].skill_terms == ["PostgreSQL", "Oracle"]
    assert any("'MongoDB' not in the quote" in w for w in card.warnings)


def test_v4_unreadable_terms_answer_keeps_the_requirement():
    sentences = [item("Experience with PostgreSQL or Oracle.")]

    def answer(text, template):
        return "garbage" if is_terms_call(template) else model(sentences, {})(text, template)

    card = run_job_agent(POST, "x", FakeBackend(answer), prompt_version="job-v4")
    assert [(r.evidence, r.skill_terms) for r in card.requirements] == [("Experience with PostgreSQL or Oracle.", [])]
    assert any(w.startswith("terms ") and "unreadable" in w for w in card.warnings)


def test_v4_invented_quote_is_not_sent_to_the_terms_call():
    sentences = [item("Experience with PostgreSQL or Oracle."), item("Ten years of COBOL on mainframes.")]
    fake = FakeBackend(model(sentences, {}))
    run_job_agent(POST, "x", fake, prompt_version="job-v4")
    assert [c["text"] for c in fake.calls if is_terms_call(c["template"])] == ["Experience with PostgreSQL or Oracle."]


def test_v3_makes_no_terms_call():
    fake = FakeBackend(model([item("Experience with PostgreSQL or Oracle.")], {}))
    run_job_agent(POST, "x", fake, prompt_version="job-v3")
    assert not any(is_terms_call(c["template"]) for c in fake.calls)


@pytest.mark.parametrize("path", GOLD, ids=lambda p: p.stem)
def test_v4_with_a_perfect_model_finds_the_gold_skill_names(path):
    """First call: one item per gold sentence, no terms (what the real model does).
    Terms call: the gold terms of that sentence. Every sentence must end with the gold terms."""
    gold = json.loads(path.read_text(encoding="utf-8"))
    sentences, terms = {}, {}
    for r in gold["requirements"]:
        sentences.setdefault(r["evidence"], {**r, "skill_terms": []})
        terms.setdefault(r["evidence"], []).extend(t for t in r["skill_terms"] if t not in terms[r["evidence"]])
    fields = ("evidence", "skill_terms", "kind", "category", "min_years", "text")
    first = [{k: s[k] for k in fields} for s in sentences.values()]
    card = run_job_agent(offer(gold["job_id"]), gold["job_id"], FakeBackend(model(first, terms)),
                         prompt_version="job-v4")

    def by_sentence(reqs):
        out = {}
        for r in reqs:
            out.setdefault(r["evidence"], set()).update(r["skill_terms"])
        return out

    assert by_sentence([r.model_dump() for r in card.requirements]) == by_sentence(gold["requirements"]), \
        card.warnings
