"""Per-requirement analysis of saved Matcher predictions (no model needed): false-MET cases and explanation quality.

  python docs/qa/analysis/val_error_analysis.py <predictions.jsonl> [<predictions.jsonl> ...] [--judge name=judged.jsonl ...]

Reads benchmark/data/val.jsonl for the CV and requirement. Outputs markdown on stdout.
false-MET (as in benchmark/metrics.py): decision MET while gold is not MET; rate = count / non-MET gold items.
"raw" uses the model's decision before the validator, "final" the validated one. "unreviewed" = final MET with
needs_human_review false (validator only; the Judge is reported separately when its judged.jsonl is given).
Explanation on-topic: names a requirement term (skill term or content word of the requirement text). Grounded: every
number in the explanation also occurs in the evidence quotes or the requirement text.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
WEAK = re.compile(r"\b(tutorials?|watched|read about|interested in|course|online course|bootcamp|familiar with|"
                  r"exposure|side projects?|over time|basic|introductory|attended)\b", re.I)
sys.path.insert(0, str(ROOT / "tests" / "qa"))
from _qa_support import explanation_grounded as grounded  # noqa: E402  (same checks as the QA tests)
from _qa_support import explanation_on_topic as on_topic  # noqa: E402


def explanation(p):
    try:
        return json.loads(p["raw"]).get("explanation") if p.get("parsed") else None
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None


def main(args):
    judges = dict(a.split("=", 1) for a in args if "=" in a)
    runs = [a for a in args if "=" not in a and not a.startswith("--")]
    cases = {c["case_id"]: c for c in map(json.loads, open(ROOT / "benchmark/data/val.jsonl"))}
    print("# Val error analysis (LIVE predictions, read from committed run files)\n")
    for run in runs:
        name = Path(run).parent.name if Path(run).name == "predictions.jsonl" else Path(run).stem
        P = [json.loads(line) for line in open(run)]
        J = {}
        for jn, jp in judges.items():
            if jn == name:
                J = {(j["case_id"], j["req_id"]): j for j in map(json.loads, open(jp))}
        neg = sum(p["gold_decision"] != "MET" for p in P)
        raw = [p for p in P if p["model_decision"] == "MET" and p["gold_decision"] != "MET"]
        fin = [p for p in raw if p["decision"] == "MET"]
        unrev = [p for p in fin if not p["needs_human_review"]]
        print(f"## {name}\n\nn={len(P)}, non-MET gold={neg}. raw false-MET {len(raw)} ({len(raw)/neg:.3f}), "
              f"final {len(fin)} ({len(fin)/neg:.3f}), final and unreviewed by the validator {len(unrev)}.\n")
        print("| case/req | gold | final | requirement | model quote | weak cue | validator reasons | judge |")
        print("|---|---|---|---|---|---|---|---|")
        for p in raw:
            c = cases[p["case_id"]]
            req = next(r for r in c["job"]["requirements"] if r["req_id"] == p["req_id"])
            q = "; ".join(p["raw_quotes"])
            j = J.get((p["case_id"], p["req_id"]), {}).get("judge_verdict", "-")
            print(f"| {p['case_id']}/{p['req_id']} | {p['gold_decision']}/{p['gold_basis']} | {p['decision']} | "
                  f"{req['text']} | {q} | {'yes' if WEAK.search(q) else ''} | {', '.join(p['review_reasons']) or '**none**'} | {j} |")
        ex = [(explanation(p), p) for p in P]
        parsed = [(e, p) for e, p in ex if e is not None]
        reqs = {(p["case_id"], p["req_id"]): next(r for r in cases[p["case_id"]]["job"]["requirements"] if r["req_id"] == p["req_id"]) for p in P}
        top = sum(on_topic(e, reqs[(p["case_id"], p["req_id"])]) for e, p in parsed)
        gr = sum(grounded(e, reqs[(p["case_id"], p["req_id"])], p["raw_quotes"]) for e, p in parsed)
        distinct = Counter(e for e, _ in parsed)
        print(f"\nExplanations: {len(distinct)} distinct over {len(parsed)} parsed; on-topic {top/len(parsed):.3f}; "
              f"numbers grounded {gr/len(parsed):.3f}. Most common: "
              + "; ".join(f"{n}x {e!r}" for e, n in distinct.most_common(2)) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
