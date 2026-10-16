"""Demo: run the full pipeline (Matcher -> Validator -> Bias Auditor -> NLI Judge -> Aggregator -> Report Writer)
on one benchmark case or on structured CV/Job JSON files. Configuration from the environment (matcher/factory.py,
config/matcher.env.example): fine-tuned LoRA Matcher with original-Qwen fallback, HS_RAG provider, NLI Judge.

  python scripts/run_pipeline.py --case val-000 --out out/val-000
  python scripts/run_pipeline.py --cv cv.json --job job.json --out out/demo
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark.run import DATA, read_jsonl  # noqa: E402
from matcher.factory import build  # noqa: E402
from matcher.pipeline import write_report  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", help="benchmark case id, e.g. val-000")
    ap.add_argument("--cv")
    ap.add_argument("--job")
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-judge", action="store_true")
    a = ap.parse_args()
    if a.case:
        c = next(c for s in ("val", "train") for c in read_jsonl(DATA / f"{s}.jsonl") if c["case_id"] == a.case)
        cv, job = c["cv"], c["job"]
    else:
        cv, job = json.loads(Path(a.cv).read_text()), json.loads(Path(a.job).read_text())
    env = dict(os.environ)
    if a.no_judge:
        env["HS_JUDGE"] = "off"
    out = build(env).run(cv, job)
    d = Path(a.out)
    d.mkdir(parents=True, exist_ok=True)
    (d / "report.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    (d / "report.md").write_text(write_report(out))
    print(f"wrote {d / 'report.json'} and {d / 'report.md'}; human review needed for {out['summary']['requires_human_review']} requirement(s)")


if __name__ == "__main__":
    main()
