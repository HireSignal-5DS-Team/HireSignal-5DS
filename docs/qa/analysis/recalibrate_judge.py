"""Re-calibrate the NLI Judge threshold after QA-017/018 (premise = quote line context, chunked whole CV).

  python docs/qa/analysis/recalibrate_judge.py --judge-dir <dir> --name <name> [--run lexical-rag-train]

Same protocol as `benchmark.judge_eval --calibrate-only`: train run, train-dev cases only (case index % 5 == 0),
tau_pass = tau_fail = tau, grid 0.30..0.95, maximise strict-flag F1. Scores BOTH premise versions with one model
load: v1 (pre-QA-017: quotes joined, whole CV truncated by the tokenizer) and v2 (current matcher/judge.py), so the
old tau is reproduced in the same run. Writes docs/qa/analysis/judge_recalibration_<name>.json. Never touches val/test.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from benchmark.judge_eval import load, metrics, probs_for, verdicts  # noqa: E402
from matcher.judge import NLIJudge, hypothesis  # noqa: E402

GRID = [round(0.3 + 0.05 * i, 2) for i in range(14)]


def probs_v1(judge, items):
    """Pre-QA-017 premises (matcher/judge.py @ 48186fd): bare quotes joined, whole CV as one (truncated) premise."""
    kinds, pairs = [], []
    for _, res, cv, req in items:
        if res.decision == "UNCERTAIN":
            kind, prem = None, None
        elif res.decision == "MISSING" and res.basis == "not_documented":
            kind, prem = "cv", cv.text
        else:
            kind, prem = ("quotes", " ".join(res.evidence)) if res.evidence else (None, None)
        kinds.append(kind)
        if kind:
            pairs.append((prem, hypothesis(req)))
    pr = iter(judge.probs(pairs))
    return [(k, next(pr) if k else None) for k in kinds]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge-dir", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--run", default="lexical-rag-train")
    a = ap.parse_args()
    judge = NLIJudge(a.judge_dir, name=a.name)
    cfg, items = load(a.run)
    assert cfg["split"] == "train", "calibrate on train-dev only"
    out = {"run": a.run, "split": "train-dev (case % 5 == 0)", "n_items": len(items), "judge": a.name,
           "judge_dir": a.judge_dir}
    for version, kp in (("v1_quote_only", probs_v1(judge, items)), ("v2_line_context_chunked", probs_for(judge, items))):
        grid = {t: metrics(items, verdicts(judge, items, kp, t))["strict"]["f1"] for t in GRID}
        best = max(grid, key=grid.get)
        m = metrics(items, verdicts(judge, items, kp, best))
        out[version] = {"tau": best, "strict_f1": grid[best], "grid_f1": grid, "auroc": m["auroc_error_detection"],
                        "n_applicable": m["n_applicable"], "n_errors": m["n_errors"],
                        "premises_changed": None}
    out["v2_line_context_chunked"]["premises_changed"] = sum(
        judge.premise(res, cv)[1] != (" ".join(res.evidence) if res.decision != "MISSING" or res.basis != "not_documented" else cv.text)
        for _, res, cv, _ in items if judge.premise(res, cv)[0])
    p = Path(__file__).parent / f"judge_recalibration_{a.name}.json"
    p.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: (v if not isinstance(v, dict) else {x: v[x] for x in ("tau", "strict_f1", "auroc")}) for k, v in out.items()}))


if __name__ == "__main__":
    main()
