"""Replay saved raw Matcher outputs through the CURRENT matcher/validate.py (no model call) and score them.

  python docs/qa/analysis/replay_validator.py --esco <esco_ict_skills.jsonl> <run-dir> [<run-dir> ...]

Each run dir holds predictions.jsonl from benchmark/run.py. RAG refs are rebuilt from their ESCO doc ids (title +
"Also known as" aliases, as RagKnowledge does). Use it to measure a validator change on real model outputs: run once
on the base commit and once with the change applied. The raw text is LIVE model output; the replay is deterministic.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from matcher import CV, Requirement  # noqa: E402
from matcher.knowledge import esco_aliases  # noqa: E402
from matcher.schemas import KnowledgeRef  # noqa: E402
from matcher.validate import parse_model_output, validate  # noqa: E402


def f1(gold, pred, labels=("MET", "MISSING", "UNCERTAIN")):
    out = []
    for lab in labels:
        tp = sum(g == lab and p == lab for g, p in zip(gold, pred))
        fp = sum(g != lab and p == lab for g, p in zip(gold, pred))
        fn = sum(g == lab and p != lab for g, p in zip(gold, pred))
        pr, rc = (tp / (tp + fp) if tp + fp else 0.0), (tp / (tp + fn) if tp + fn else 0.0)
        out.append(2 * pr * rc / (pr + rc) if pr + rc else 0.0)
    return sum(out) / len(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--esco", required=True)
    ap.add_argument("runs", nargs="+")
    a = ap.parse_args()
    esco = {e["doc_id"]: e for e in map(json.loads, open(a.esco))}
    cases = {c["case_id"]: c for s in ("val", "test") for c in map(json.loads, open(ROOT / f"benchmark/data/{s}.jsonl"))}
    print("| run | macro-F1 | false-MET | unreviewed false-MET | MET reviewed | review rate | changed vs saved |")
    print("|---|---|---|---|---|---|---|")
    for run in a.runs:
        P = [json.loads(line) for line in open(Path(run) / "predictions.jsonl")]
        gold, pred, rows, changed = [], [], [], 0
        for p in P:
            c = cases[p["case_id"]]
            req = Requirement(**next(r for r in c["job"]["requirements"] if r["req_id"] == p["req_id"]))
            refs = [KnowledgeRef(source_type="esco", source_id=i, title=esco[i]["title"], text=esco[i]["text"],
                                 url=esco[i].get("url"), aliases=esco_aliases(esco[i]["text"]), retrieval="replay")
                    for i in p.get("rag_refs") or [] if i in esco]
            r = validate(parse_model_output(p["raw"]), CV(**c["cv"]), req, refs)
            changed += r.decision != p["decision"]
            gold.append(p["gold_decision"]), pred.append(r.decision), rows.append(r)
        neg = sum(g != "MET" for g in gold)
        fm = [r for g, r in zip(gold, rows) if g != "MET" and r.decision == "MET"]
        met = [r for r in rows if r.decision == "MET"]
        print(f"| {Path(run).name} | {f1(gold, pred):.3f} | {len(fm)/neg:.3f} ({len(fm)}) | "
              f"{sum(not r.needs_human_review for r in fm)} | {sum(r.needs_human_review for r in met)}/{len(met)} | "
              f"{sum(r.needs_human_review for r in rows)/len(rows):.3f} | {changed} |")


if __name__ == "__main__":
    main()
