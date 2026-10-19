r"""T09b Part B: apply the Approver's review (rag/eval/queries_review.xlsx, sheet "Review") to rag/eval/queries.jsonl.

Column H DECISION: OK -> keep the gold; CHANGE -> gold = the labels in column I (" | "-separated, exact ESCO labels);
DROP -> remove the query. The pre-review file is kept once as rag/eval/queries_drafted.jsonl.

Usage: .venv\Scripts\python scripts\apply_query_review.py
"""
import json
import shutil
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rag.retrieval import load_concepts  # noqa: E402

QUERIES = ROOT / "rag/eval/queries.jsonl"
DRAFTED = ROOT / "rag/eval/queries_drafted.jsonl"
NOTE = "; checked by the Approver 2026-10-18"


def main():
    if not DRAFTED.exists():
        shutil.copy(QUERIES, DRAFTED)
    queries = [json.loads(line) for line in open(DRAFTED, encoding="utf-8")]
    ws = openpyxl.load_workbook(ROOT / "rag/eval/queries_review.xlsx", read_only=True, data_only=True)["Review"]
    review = {r[0]: r for r in list(ws.iter_rows(values_only=True))[1:] if r and r[0]}
    drafted = [q for q in queries if q["qid"] in review]
    missing = [q["qid"] for q in drafted if not (review[q["qid"]][7] or "").strip()]
    if len(drafted) != len(review) or missing:
        sys.exit(f"review incomplete: {len(review)} rows, {len(drafted)} matched, no DECISION for {missing}")
    uri = {}
    for c in load_concepts():
        uri.setdefault(c["label"], c["uri"])
    out, counts, unmatched = [], {"OK": 0, "CHANGE": 0, "DROP": 0}, []
    for q in queries:
        r = review.get(q["qid"])
        if r is None:
            out.append(q)
            continue
        decision = r[7].strip().upper()
        counts[decision] += 1
        if decision == "DROP":
            continue
        if decision == "CHANGE":
            labels = [x.strip() for x in (r[8] or "").split("|") if x.strip()]
            unmatched += [f"{q['qid']}: {x}" for x in labels if x not in uri]
            labels = [x for x in labels if x in uri]
            q = q | {"gold_labels": labels, "gold_uris": [uri[x] for x in labels]}
        out.append(q | {"how_made": q["how_made"] + NOTE})
    with open(QUERIES, "w", encoding="utf-8") as f:
        for q in out:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    print(counts, "queries:", len(out), "unmatched labels:", unmatched or "none")


if __name__ == "__main__":
    main()
