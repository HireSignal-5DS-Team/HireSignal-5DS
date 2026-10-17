"""Job Agent evaluation: gold cards, scoring, and guardrails/annotation consistency."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.job import FakeBackend, run_job_agent  # noqa: E402
from agents.job import prompts  # noqa: E402
from agents.job.scoring import score_card  # noqa: E402

GOLD = sorted((ROOT / "eval/job_agent/gold").glob("*.json"))
FIELDS = ("evidence", "skill_terms", "kind", "category", "min_years", "text")


@pytest.fixture(autouse=True)
def whole_offer_prompt(monkeypatch):
    """The gold round-trip gives the fake model ONE whole-offer answer: the job-v2 path.
    The same check for the chunked path is in test_job_v3.py / test_job_v4.py."""
    monkeypatch.setattr(prompts, "PROMPT_VERSION", "job-v2")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_there_are_ten_gold_cards():
    assert len(GOLD) == 10


def test_gold_cards_pass_the_checker():
    result = subprocess.run([sys.executable, str(ROOT / "scripts/check_gold.py")], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("path", GOLD, ids=lambda p: p.stem)
def test_gold_through_the_agent_gives_back_the_gold(path):
    """If the model answered exactly the gold card, the guardrails must not change it.

    This keeps the code (split, years, must/nice repairs) consistent with ANNOTATION_RULES.md.
    """
    gold = load(path)
    post = (ROOT / "eval/job_agent/offers" / f"{gold['job_id']}.txt").read_text(encoding="utf-8")
    answer = json.dumps({"title": gold["title"],
                         "requirements": [{k: r[k] for k in FIELDS} for r in gold["requirements"]]})
    card = run_job_agent(post, gold["job_id"], FakeBackend([answer]))
    got = [(r.evidence, r.skill_terms, r.kind, r.category, r.min_years) for r in card.requirements]
    want = [(r["evidence"], r["skill_terms"], r["kind"], r["category"], r["min_years"]) for r in gold["requirements"]]
    assert got == want, card.warnings


# ------------------------------------------------------------------ scoring ---

def r(req_id, evidence, terms=(), kind="must", category="skill", years=None, text=None):
    return {"req_id": req_id, "text": text or evidence, "evidence": evidence, "kind": kind,
            "category": category, "skill_terms": list(terms), "min_years": years}


GOLD_REQS = [
    r("r1", "At least 3 years with Java and Spring Boot.", ["Java"], category="experience", years=3),
    r("r2", "At least 3 years with Java and Spring Boot.", ["Spring Boot"], category="experience", years=3),
    r("r3", "Docker is a plus.", ["Docker"], kind="nice"),
]


def test_perfect_prediction():
    s = score_card(GOLD_REQS, GOLD_REQS)
    assert (s.tp, s.fp, s.fn) == (3, 0, 0) and s.f1 == 1.0


def test_missing_and_extra_are_counted():
    pred = [GOLD_REQS[0], r("p9", "Kubernetes required.", ["Kubernetes"])]
    s = score_card(pred, GOLD_REQS)
    assert (s.tp, s.fp, s.fn) == (1, 1, 2)
    assert s.unmatched_gold == ["r2", "r3"] and s.unmatched_pred == ["p9"]


def test_same_quote_but_different_skill_does_not_match():
    pred = [r("p1", "At least 3 years with Java and Spring Boot.", ["Spring Boot"], category="experience", years=3)]
    s = score_card(pred, [GOLD_REQS[0]])
    assert s.tp == 0


def test_longer_quote_still_matches_and_wrong_kind_is_counted():
    pred = [r("p1", "Nice to have: Docker is a plus.", ["Docker"], kind="must")]
    s = score_card(pred, [GOLD_REQS[2]])
    assert s.tp == 1 and s.kind_ok == 0


def test_each_gold_matches_at_most_once():
    pred = [GOLD_REQS[2], {**GOLD_REQS[2], "req_id": "dup"}]
    s = score_card(pred, [GOLD_REQS[2]])
    assert (s.tp, s.fp) == (1, 1)


# --------------------------------------------------------- two-level scoring ---

from agents.job.scoring import score_sentences, score_skill_terms  # noqa: E402


def test_found_sentence_without_skill_names_counts_as_found():
    """Real evaluation: the model found the right sentence but left skill_terms empty."""
    pred = [r("p1", "At least 3 years with Java and Spring Boot.", [], category="experience", years=3)]
    sent, pairs = score_sentences(pred, GOLD_REQS)
    assert (sent.tp, sent.fp, sent.fn) == (1, 0, 1)            # 2 gold sentences: one found
    terms = score_skill_terms(pred, GOLD_REQS, pairs)
    assert (terms.tp, terms.fp, terms.fn) == (0, 0, 2)         # Java and Spring Boot not named
    strict = score_card(pred, GOLD_REQS)
    assert strict.tp == 0                                      # the strict score sees nothing


def test_skill_terms_are_compared_per_sentence():
    pred = [r("p1", "At least 3 years with Java and Spring Boot.", ["Java", "Kotlin"], category="experience")]
    _, pairs = score_sentences(pred, GOLD_REQS)
    terms = score_skill_terms(pred, GOLD_REQS, pairs)
    assert (terms.tp, terms.fp, terms.fn) == (1, 1, 1)         # Java right, Kotlin wrong, Spring Boot missing


def test_each_sentence_matches_once():
    pred = [r("p1", "Docker is a plus.", ["Docker"], kind="nice"), r("p2", "Docker is a plus", ["Docker"], kind="nice")]
    sent, _ = score_sentences(pred, GOLD_REQS)
    assert (sent.tp, sent.fp) == (1, 1)


def test_recording_backend_keeps_every_answer():
    sys.path.insert(0, str(ROOT / "scripts"))
    from eval_job_agent import RecordingBackend
    rec = RecordingBackend(FakeBackend(["A", "B"]))
    rec.extract("first chunk", "{}", [])
    rec.extract("second chunk", "{}", [])
    dump = rec.dump()
    assert "### call 1" in dump and "### call 2" in dump and "first chunk" in dump and dump.endswith("B")
