"""rag_opt scripts without any model: MOCK arm runs, the paired report and the error analysis."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import benchmark.run as bench  # noqa: E402
from rag_opt import e2e_report, run_arm  # noqa: E402
from rag_opt.error_analysis import echo  # noqa: E402


def test_mock_arms_run_through_the_frozen_loop_and_report(tmp_path):
    original = bench.RagKnowledge
    for arm in ("none", "bm25", "gated"):
        run_arm.main(["--arm", arm, "--backend", "mock_gold", "--split", "val", "--limit", "2",
                      "--run-id", f"mock__{arm}", "--out-root", str(tmp_path)])
    assert bench.RagKnowledge is original  # the provider swap does not leak
    cfg = json.loads((tmp_path / "mock__gated/config.json").read_text())
    prov = json.loads((tmp_path / "mock__gated/provenance.json").read_text())
    assert cfg["knowledge"].startswith("rag.gated.v1") and prov["label"].startswith("MOCK")
    recs = [json.loads(x) for x in (tmp_path / "mock__gated/predictions.jsonl").read_text().splitlines()]
    gated_cats = {"certification", "language", "education"}
    data = {(c["case_id"], r["req_id"]): r for c in map(json.loads, (ROOT / "benchmark/data/val.jsonl").read_text().splitlines()[:2])
            for r in c["job"]["requirements"]}
    assert all(not r["rag_refs"] for r in recs if data[(r["case_id"], r["req_id"])]["category"] in gated_cats)
    out = e2e_report.report({"mock": {a: tmp_path / f"mock__{a}" for a in ("none", "bm25", "gated")}})
    assert set(out["mock"]["paired"]) == {"bm25 vs none", "gated vs none", "gated vs bm25"}
    assert all(s["label"].startswith("MOCK") for s in out["mock"]["runs"].values())


def test_run_arm_refuses_test_split_and_manual_knowledge(tmp_path):
    with pytest.raises(SystemExit):
        run_arm.main(["--arm", "gated", "--backend", "mock_gold", "--split", "test", "--run-id", "x", "--out-root", str(tmp_path)])
    with pytest.raises(SystemExit):
        run_arm.main(["--arm", "gated", "--backend", "mock_gold", "--knowledge", "none", "--run-id", "x", "--out-root", str(tmp_path)])


def test_template_echo_detector():
    ok = {"parsed": True, "raw": '{"decision": "MET"}'}
    bad = {"parsed": False, "raw": '{"decision": "MET|MISSING|UNCERTAIN", "basis": "supported|contradicted"}'}
    trunc = {"parsed": False, "raw": '{"decision": "MET", "evid'}
    assert (echo(ok), echo(bad), echo(trunc)) == (False, True, False)


def test_e2e_report_reproduces_the_audit_numbers():
    """Recorded LIVE runs of the RAG audit (base Qwen3-4B Q4): Δ macro-F1 BM25 vs none = -0.041 [-0.083, -0.000]."""
    ri = ROOT / "rag/integration/results"
    out = e2e_report.report({"base": {"none": ri / "qwen3-4b-q4-none-val-rerun", "bm25": ri / "qwen3-4b-q4-bm25-val-rerun"}})
    p = out["base"]["paired"]["bm25 vs none"]
    assert round(p["delta_macro_f1"], 3) == -0.041 and [round(x, 3) for x in p["ci95"]] == [-0.083, -0.0]
    assert p["mcnemar_p"] == 0.0931 and (p["base_only_correct"], p["cand_only_correct"]) == (16, 7)
