"""Verdict changes caused by the QA-017/018 premise change, at a FIXED tau (evaluation only, nothing is fitted).

  python docs/qa/analysis/judge_premise_effect.py --judge-dir <dir> --name <name> --tau 0.65 --run <run> [...]
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
from benchmark.judge_eval import load, probs_for, verdicts  # noqa: E402
from matcher.judge import NLIJudge  # noqa: E402
from recalibrate_judge import probs_v1  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge-dir", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--tau", type=float, required=True)
    ap.add_argument("--run", action="append", required=True)
    ap.add_argument("--root", help="results root holding <run>/{config.json,predictions.jsonl} (default benchmark/results)")
    a = ap.parse_args()
    if a.root:
        import benchmark.judge_eval as je
        je.ROOT = Path(a.root)
    judge = NLIJudge(a.judge_dir, name=a.name)
    out = {"judge": a.name, "tau": a.tau, "results_root": a.root or "benchmark/results", "runs": {}}
    for run in a.run:
        _, items = load(run)
        v1 = verdicts(judge, items, probs_v1(judge, items), a.tau)
        v2 = verdicts(judge, items, probs_for(judge, items), a.tau)
        changed = [(r["case_id"], r["req_id"], x.judge_verdict, y.judge_verdict) for (r, *_), x, y in zip(items, v1, v2)
                   if x.judge_verdict != y.judge_verdict]
        out["runs"][run] = {"n": len(items), "verdicts_changed": len(changed), "changes": changed}
    p = Path(__file__).parent / f"judge_premise_effect_{a.name}.json"
    p.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({r: v["verdicts_changed"] for r, v in out["runs"].items()}))


if __name__ == "__main__":
    main()
