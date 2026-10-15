import json
from pathlib import Path

import pytest

from benchmark import make_dataset, metrics, run

DATA = Path(__file__).parents[1] / "data"


@pytest.fixture(scope="module")
def splits():
    return {s: run.read_jsonl(DATA / f"{s}.jsonl") for s in ("train", "val", "test")}


def test_generator_is_deterministic_and_matches_manifest(tmp_path):
    m = make_dataset.write(tmp_path)
    committed = json.loads((DATA / "MANIFEST.json").read_text())
    assert {s: v["sha256"] for s, v in m["splits"].items()} == {s: v["sha256"] for s, v in committed["splits"].items()}
    for s, v in committed["splits"].items():
        assert make_dataset.sha256(DATA / v["file"]) == v["sha256"], f"{s} file changed without regenerating MANIFEST"
    assert "LOCKED" in committed["note"]


def test_gold_quotes_are_exact_cv_substrings(splits):
    for cases in splits.values():
        for c in cases:
            for g in c["gold"].values():
                assert all(q in c["cv"]["text"] for q in g["evidence"])
                assert (g["evidence"] != []) == (g["basis"] in ("supported", "contradicted"))


def test_splits_are_disjoint(splits):
    texts = {s: {c["cv"]["text"] for c in cases} for s, cases in splits.items()}
    lines = {s: {ln.lstrip("-•*– ") for t in texts[s] for ln in t.splitlines() if len(ln) > 25} for s in splits}
    reqs = {s: {r["text"] for c in cases for r in c["job"]["requirements"]} for s, cases in splits.items()}
    for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
        assert not texts[a] & texts[b]
        assert not reqs[a] & reqs[b], (a, b, reqs[a] & reqs[b])
        shared = lines[a] & lines[b]
        assert not shared, (a, b, list(shared)[:3])
    ids = [c["case_id"] for cases in splits.values() for c in cases]
    assert len(ids) == len(set(ids))


def test_hard_case_coverage(splits):
    need = ["equivalent_skill_alias", "implicit_project_evidence", "missing_evidence", "contradictory_evidence",
            "insufficient_experience", "ambiguous_duration", "multi_requirement", "distractor_details",
            "rag_suggests_absent_skill", "negation_trap"]
    for s in ("val", "test"):
        tags = [t for c in splits[s] for g in c["gold"].values() for t in g["tags"]]
        for t in need:
            assert tags.count(t) >= 5, (s, t, tags.count(t))


def test_metrics_hand_computed():
    gold = ["MET", "MET", "MISSING", "UNCERTAIN"]
    pred = ["MET", "MISSING", "MET", None]
    m = metrics.decision_metrics(gold, pred)
    assert m["per_class"]["MET"] == {"precision": 0.5, "recall": 0.5, "f1": 0.5, "support": 2}
    assert m["per_class"]["UNCERTAIN"]["recall"] == 0.0
    assert m["false_met_rate"] == 0.5  # 1 of the 2 non-MET items predicted MET
    assert m["accuracy"] == 0.25
    assert m["confusion"]["UNCERTAIN"][None] == 1


def test_runner_mock_and_resume(tmp_path):
    args = ["--backend", "mock_gold", "--split", "val", "--knowledge", "none", "--limit", "3", "--run-id", "t",
            "--out-root", str(tmp_path)]
    m = run.run(run.parse_args(args))
    assert m["final"]["macro_f1"] == 1.0 and m["final"]["false_met_rate"] == 0.0
    pred = tmp_path / "t/predictions.jsonl"
    n = len(pred.read_text().splitlines())
    run.run(run.parse_args(args))
    assert len(pred.read_text().splitlines()) == n  # resume adds nothing
    assert "MOCK" in (tmp_path / "t/metrics.md").read_text()
    with pytest.raises(SystemExit):  # a different configuration into the same run id is refused
        run.run(run.parse_args([*args, "--k", "5"]))


def test_test_split_needs_explicit_flag():
    with pytest.raises(SystemExit):
        run.parse_args(["--backend", "lexical", "--split", "test", "--run-id", "x"])
