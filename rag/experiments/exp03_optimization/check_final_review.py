"""Validate a filled final-test review sheet WITHOUT running any retrieval or evaluation.

    python check_final_review.py [sheet.csv]     (default: final_test_review_sheet.csv)

Checks: all 36 sealed qids present exactly once, decision in ACCEPT / CORRECT / REJECT, reviewer named,
CORRECT rows carry a corrected gold that exists in the sources (verbatim quote / ESCO label), and the sealed test
file still has its committed SHA256. Lists unresolved rows. Exit code 1 if anything is unresolved or invalid.
"""
import csv
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))
from corpus import load_esco, load_jobs  # noqa: E402

SEALED_SHA = "0a14b0cdf313a3f942903b408f07be59c72c549e68b7968f3910eb8f47e8214d"
DEC = "decision (ACCEPT/CORRECT/REJECT)"


def main(sheet):
    test = HERE / "final_test_queries.jsonl"
    problems, unresolved = [], []
    if hashlib.sha256(test.read_bytes()).hexdigest() != SEALED_SHA:
        problems.append("sealed final_test_queries.jsonl changed since it was committed")
    qs = {q["qid"]: q for q in map(json.loads, open(test, encoding="utf-8"))}
    rows = list(csv.DictReader(open(sheet, encoding="utf-8-sig")))
    ids = [r.get("qid") for r in rows]
    missing, extra = set(qs) - set(ids), set(ids) - set(qs)
    dup = {i for i in ids if ids.count(i) > 1}
    for name, s in (("missing", missing), ("unknown", extra), ("duplicate", dup)):
        if s:
            problems.append(f"{name} qids: {sorted(s)}")
    jobs = {j["doc_id"]: j["text"] for j in load_jobs()}
    labels = {e["title"] for e in load_esco()}
    counts = {}
    for r in rows:
        d = (r.get(DEC) or "").strip().upper()
        counts[d or "(blank)"] = counts.get(d or "(blank)", 0) + 1
        q = qs.get(r["qid"])
        if d not in ("ACCEPT", "CORRECT", "REJECT"):
            unresolved.append(f"{r['qid']}: no valid decision ({d or 'blank'}) {r.get('notes', '')[:80]}")
            continue
        if not (r.get("reviewer") or "").strip():
            unresolved.append(f"{r['qid']}: reviewer not named")
        if d == "CORRECT" and q:
            new = [g.strip() for g in (r.get("corrected_gold") or "").split("||") if g.strip()]
            ok = new and all((g in jobs[q["job_id"]]) if q["type"] == "job" else (g in labels or g == "no_match") for g in new)
            if not ok:
                unresolved.append(f"{r['qid']}: CORRECT without a corrected gold found in the sources: {new}")
    print(f"rows: {len(rows)}; decisions: {counts}")
    for p in problems + unresolved:
        print(" -", p)
    print("VALID AND COMPLETE" if not (problems or unresolved) else f"NOT READY: {len(problems)} format problems, {len(unresolved)} unresolved rows")
    return 1 if problems or unresolved else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "final_test_review_sheet.csv"))
