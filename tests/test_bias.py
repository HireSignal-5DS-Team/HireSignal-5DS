"""T11 Bias Auditor: counterfactual generator, leakage lexicon, bare-name fix, swap_flip -> review, BIAS_SWAP paths."""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from make_counterfactuals import build, variants  # noqa: E402
from services import api  # noqa: E402
from services.bias.auditor import SWAP_FLIP, counterfactual, leakage_check  # noqa: E402
from services.outcome.gate import decide  # noqa: E402
from services.profile import anonymise_cv  # noqa: E402

BASE = "Position: Data Engineer\nExperience years: 4\nEnglish level: upper\n\nI build ETL pipelines in Python and SQL."


@pytest.mark.parametrize("index", [0, 1, 2])
def test_generator_only_adds_identity_lines(index):
    for vid, v in variants(index).items():
        text = build(BASE, v["lines"])
        assert text.endswith(BASE) and text[: -len(BASE)] == "\n".join(v["lines"]) + "\n"
        assert "Experience years: 4" in text and "English level: upper" in text  # job-relevant lines untouched


def test_generated_bases_equal_the_source_cvs():
    manifest = ROOT / "data/processed/counterfactuals/manifest.json"
    if not manifest.exists():
        pytest.skip("counterfactual set not generated")
    m = json.loads(manifest.read_text(encoding="utf-8"))
    for pid, info in list(m["pairs"].items())[:5]:
        src = (ROOT / "data/processed/cvs" / info["cv_file"]).read_text(encoding="utf-8")
        assert (manifest.parent / pid / "base.txt").read_text(encoding="utf-8") == src


@pytest.mark.parametrize("line,kind", [("Nationality: Tunisian", "nationality"), ("Date of birth: 14/03/1971", "birth"),
                                       ("Marital status: married, 2 children", "family"),
                                       ("Native language: Arabic", "language_native"), ("Pronouns: she/her", "gender"),
                                       ("Religion: Muslim", "religion")])
def test_protected_label_lines_are_removed(line, kind):
    text, flags = leakage_check(f"{line}\n{BASE}")
    assert text == BASE and flags[0]["kind"] == kind and flags[0]["action"] == "line removed"
    assert line.split(":")[1].strip() not in json.dumps(flags)  # flags never carry the protected value


def test_placeholder_only_lines_are_removed_but_job_lines_stay():
    text, flags = leakage_check(f"[NAME]\nLocation: [ADDRESS]\n[EMAIL] | [PHONE]\nLocation: Remote (EU)\n"
                                f"Languages: German (B2), English (C1)\n{BASE}")
    assert text == f"Location: Remote (EU)\nLanguages: German (B2), English (C1)\n{BASE}"
    assert [f["rule"] for f in flags] == ["placeholder-only line"] * 3


def test_protected_words_in_running_text_are_masked():
    text, flags = leakage_check("I am married and 34 years old. Built Spark jobs.")
    assert text == "I am [PERSONAL] and 34 [PERSONAL]. Built Spark jobs." and len(flags) == 2


def test_lexicon_keeps_the_dev_base_cvs_job_text():
    """Tuned on dev only: on the dev base CVs the check may only remove identity placeholder lines."""
    manifest = ROOT / "data/processed/counterfactuals/manifest.json"
    if not manifest.exists():
        pytest.skip("counterfactual set not generated")
    m = json.loads(manifest.read_text(encoding="utf-8"))
    from services.reader import read_cv
    for pid, info in m["pairs"].items():
        if info["split"] != "dev":
            continue
        r = read_cv((manifest.parent / pid / "base.txt").read_bytes(), "cv.txt")
        _, flags = leakage_check(anonymise_cv(r.text, cv_id="cv-00000000", sections=r.sections).text)
        assert all(f["rule"] == "placeholder-only line" for f in flags), (pid, flags)


def test_bare_name_on_a_cv_without_headings_is_hidden_and_stored():
    out = anonymise_cv(f"Fatma Trabelsi\nPronouns: she/her\n{BASE}", cv_id="cv-00000000")
    assert out.identity.name == "Fatma Trabelsi" and "Fatma" not in out.text
    assert leakage_check(out.text)[0] == leakage_check(anonymise_cv(BASE, cv_id="cv-00000000").text)[0]


def test_tech_first_line_is_still_not_a_name():
    out = anonymise_cv("Spark Streaming\nPosition: Data Engineer\nKafka and Spark Streaming jobs.", cv_id="cv-00000000")
    assert out.identity.name is None and "Spark Streaming" in out.text


def test_counterfactual_replaces_the_name_or_adds_one():
    text, info = counterfactual("Fatma Trabelsi\nPronouns: she/her\nPython", "Fatma Trabelsi")
    assert text == "James Miller\nPronouns: he/him\nPython" and info["counterfactual"] == "male_western"
    text, info = counterfactual(BASE, None)
    assert text.startswith("Fatma Trabelsi\nPronouns: she/her\n") and text.endswith(BASE)


def test_swap_flip_forces_review():
    reqs = [{"req_id": "r1", "kind": "must", "decision": "MET", "review_reasons": [], "confidence": {"MET": 1.0}}]
    assert decide(reqs, [], t_invite=80).outcome == "invite"
    res = decide(reqs, [SWAP_FLIP], t_invite=80, pair_flags="info")
    assert res.outcome == "review" and res.rule.startswith("0 review: identity swap")


@pytest.fixture
def bias_client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "PRIVATE", tmp_path)
    cv_id = "cv-0000abcd"
    (tmp_path / f"{cv_id}.reader.json").write_text(json.dumps({"text": BASE, "sections": {}}), encoding="utf-8")
    body = {"cv_id": cv_id, "requirements": [{"req_id": "r1", "text": "Python", "kind": "must", "skill_terms": ["Python"]}],
            "results": [{"req_id": "r1", "kind": "must", "decision": "MET", "review_reasons": [],
                         "confidence": {"MET": 1.0}}]}
    return TestClient(api.app), body


def test_bias_swap_off_skips(bias_client, monkeypatch):
    c, body = bias_client
    monkeypatch.setenv("BIAS_SWAP", "off")
    out = c.post("/bias", json=body).json()
    assert out["would_be_outcome"] == "invite" and out["swap"] == {"ran": False, "skipped": "BIAS_SWAP=off"}
    assert out["review_reasons"] == []


def test_bias_swap_identical_input_needs_no_llm(bias_client, monkeypatch):
    c, body = bias_client
    monkeypatch.setattr(api, "match", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM call expected")))
    out = c.post("/bias", json=body).json()
    assert out["swap"]["ran"] and out["swap"]["identical_matcher_input"] and out["review_reasons"] == []


def test_bias_swap_flip_when_the_input_differs_and_a_decision_changes(bias_client, monkeypatch):
    c, body = bias_client
    import services.bias.auditor as aud
    monkeypatch.setattr(api, "counterfactual", lambda raw, name: ("Native lang Arabic speaker\n" + raw,
                                                                  {"counterfactual": "test", "how": "test"}))
    monkeypatch.setattr(api, "match", lambda cv, req, refs=None: {"decision": "MISSING", "review_reasons": [],
                                                                    "evidence": [], "basis": "not_documented"})
    monkeypatch.setattr(api, "_rag_refs", lambda req, cv: [])
    monkeypatch.setattr(api, "_judge", lambda: type("J", (), {"judge": lambda self, *a: {}})())
    out = c.post("/bias", json=body).json()
    assert not out["swap"]["identical_matcher_input"] and out["swap"]["changed_must"] == ["r1"]
    assert out["review_reasons"] == [aud.SWAP_FLIP]
