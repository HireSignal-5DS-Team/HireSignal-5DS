import json
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BENCH.parent))
sys.path.insert(0, str(BENCH))

import check_data  # noqa: E402
import metrics as M  # noqa: E402
import run  # noqa: E402

CV_TEXT = "Python developer, 5 years.\nNo Terraform experience.\nSome Docker."


def rec(gold, pred, model=None, ev=(), raw_ev=(), parsed=True, tags=("exact",), gold_ev=()):
    spans = [[CV_TEXT.find(q), CV_TEXT.find(q) + len(q)] for q in ev]
    raw = json.dumps({"decision": model or pred, "basis": "supported" if (model or pred) == "MET" else "ambiguous",
                      "evidence": list(raw_ev), "explanation": "x"}) if parsed else "not json"
    return {"case_id": "c1", "req_id": "r", "latency_s": 0.5, "parsed": parsed, "raw": raw,
            "gold": {"decision": gold, "basis": "x", "evidence": list(gold_ev), "tags": list(tags)},
            "result": {"decision": pred, "basis": "x", "evidence": list(ev), "evidence_spans": spans,
                       "model_decision": (model or pred) if parsed else None}}


def test_metrics_hand_computed():
    recs = [
        rec("MET", "MET", ev=["Python developer, 5 years."], raw_ev=["Python developer, 5 years."],
            gold_ev=["Python developer"]),
        rec("MET", "MISSING", tags=("equivalence",), gold_ev=["Some Docker."]),
        rec("MISSING", "MET", ev=["No Terraform experience."], raw_ev=["No Terraform experience.", "invented quote"],
            tags=("negation",)),
        rec("UNCERTAIN", "UNCERTAIN", parsed=False),
    ]
    m = M.compute(recs, {"c1": CV_TEXT})
    f = m["final"]
    assert f["accuracy"] == 0.5
    assert f["per_class"]["MET"] == {"precision": 0.5, "recall": 0.5, "f1": 0.5, "support": 2}
    assert f["per_class"]["MISSING"]["f1"] == 0.0 and f["per_class"]["UNCERTAIN"]["f1"] == 1.0
    assert f["macro_f1"] == pytest.approx(0.5)
    assert f["false_met_rate"] == 0.5  # 1 predicted MET among 2 gold non-MET
    assert f["confusion"]["MET"] == {"MET": 1, "MISSING": 1, "UNCERTAIN": 0}
    assert f["uncertain_recall"] == 1.0 and f["predicted_uncertain_share"] == 0.25
    assert f["unsupported_met"] == 0
    r = m["raw_model"]
    assert r["json_validity"] == 0.75 and r["confusion"]["UNCERTAIN"]["INVALID"] == 1 and r["accuracy"] == 0.25
    assert r["quotes_emitted"] == 3 and r["quote_verbatim_rate"] == pytest.approx(2 / 3)
    assert m["per_tag"]["exact"] == {"n": 2, "accuracy": 1.0} and m["per_tag"]["negation"]["accuracy"] == 0.0
    assert m["evidence_overlap_gold_met"] == 0.5
    assert m["latency"]["mean_s"] == 0.5


def test_unsupported_met_counted():
    bad = rec("MET", "MET", ev=[])
    assert M.compute([bad], {"c1": CV_TEXT})["final"]["unsupported_met"] == 1


def test_check_data_passes():
    errs, splits = check_data.check(BENCH / "data")
    assert errs == []
    assert len(splits["val"]) == 14 and len(splits["test"]) == 14 and len(splits["train"]) >= 300


def test_check_data_catches_bad_evidence(tmp_path):
    for s in ("train", "val", "test"):
        (tmp_path / f"{s}.jsonl").write_text((BENCH / "data" / f"{s}.jsonl").read_text())
    lines = (tmp_path / "val.jsonl").read_text().splitlines()
    case = json.loads(lines[0])
    rid = next(k for k, g in case["gold"].items() if g["decision"] == "MET")
    case["gold"][rid]["evidence"] = ["not in the cv at all"]
    (tmp_path / "val.jsonl").write_text("\n".join([json.dumps(case)] + lines[1:]) + "\n")
    errs, _ = check_data.check(tmp_path)
    assert any("evidence not a substring" in e for e in errs)


def test_run_lexical_limit_and_resume(tmp_path, capsys):
    out = tmp_path / "lex"
    argv = ["--split", "val", "--backend", "lexical", "--knowledge", "none", "--limit", "3", "--out", str(out)]
    run.main(argv)
    assert {p.name for p in out.iterdir()} == {"predictions.jsonl", "metrics.json", "summary.md"}
    assert len((out / "predictions.jsonl").read_text().splitlines()) == 3
    assert json.loads((out / "metrics.json").read_text())["metrics"]["n"] == 3
    capsys.readouterr()
    run.main(argv)
    assert "3 already done, 0 to run" in capsys.readouterr().out
    assert len((out / "predictions.jsonl").read_text().splitlines()) == 3


def test_resume_survives_torn_and_duplicate_lines(tmp_path, capsys):
    out = tmp_path / "lex"
    argv = ["--split", "val", "--backend", "lexical", "--knowledge", "none", "--limit", "3", "--out", str(out)]
    run.main(argv)
    p = out / "predictions.jsonl"
    p.write_text(p.read_text() + p.read_text().splitlines()[0] + "\n" + '{"case_id": "va')
    run.main(argv)
    assert len(p.read_text().splitlines()) == 3
    assert json.loads((out / "metrics.json").read_text())["metrics"]["n"] == 3


def test_test_split_is_locked(tmp_path):
    with pytest.raises(SystemExit):
        run.main(["--split", "test", "--backend", "lexical", "--out", str(tmp_path / "t")])
