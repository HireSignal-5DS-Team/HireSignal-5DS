r"""T12: decision records for the Report Writer evaluation (services/report/record.py format).

One record per gold pair from the T09 V6 rows (eval/results/2026-10-18_rag_matcher/rows_V6.jsonl: production
Matcher + Judge on the 52 pairs), the outcome from the T08b gate (eval_rag_matcher.GATE). Plus, per split, two copies
with flags added in code (documented, `synthetic_flags`): a Reader image-quality flag (as from a bad photo) and an
identity-swap flip; both make the gate answer review (rule 0). Split = the gold split. No identity: quotes come from
the anonymised CV text.

Output: data/processed/report_records/<split>/<id>.json
Usage: .venv\Scripts\python scripts\make_report_records.py
"""
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from eval_rag_matcher import GATE  # noqa: E402
from services.matcher.validate import evidence_years  # noqa: E402
from services.outcome.gate import decide  # noqa: E402
from services.report.record import build_record  # noqa: E402

ROWS = ROOT / "eval/results/2026-10-18_rag_matcher/rows_V6.jsonl"
OUT = ROOT / "data/processed/report_records"
TITLES = {}


def job_title(job: str) -> str:
    if job not in TITLES:
        TITLES[job] = json.loads((ROOT / f"data/processed/jobs/{job}_requirements.json").read_text(encoding="utf-8")).get(
            "title") or job
    return TITLES[job]


def record_for(rows, reader=None, bias=None):
    reqs = [{"req_id": r["req_id"], "kind": r["kind"], "text": r["requirement"], "decision": r["pred"],
             "quotes": [q["quote"] for q in r["quotes"]], "judge": r["judge"]["verdict"],
             "review_reasons": r["review_reasons"], "skill_terms": r["skill_terms"], "min_years": r["min_years"],
             "evidence_years": evidence_years([q["quote"] for q in r["quotes"]]) if r["min_years"] and r["quotes"] else None,
             "confidence": (r["confidence"] or {}).get("normalized"), "info_flags": r["info_flags"],
             "category": r["category"]} for r in rows]
    pair_reasons = (reader or {}).get("review_reasons", []) + (bias or {}).get("review_reasons", [])
    g = decide([{**q, "judge": {"verdict": q["judge"]}} for q in reqs], pair_reasons, [], **GATE)
    return build_record(reqs, {"outcome": g.outcome, "score": g.score, "rule": g.rule, "reasons": g.reasons},
                        reader, bias, job_title(rows[0]["job"]))


def main():
    by_pair = collections.defaultdict(list)
    for line in open(ROWS, encoding="utf-8"):
        r = json.loads(line)
        by_pair[r["pair_id"]].append(r)
    out = collections.Counter()
    for split in ("dev", "test"):
        (OUT / split).mkdir(parents=True, exist_ok=True)
    flagged = {"dev": [], "test": []}
    for pid, rows in sorted(by_pair.items()):
        split = rows[0]["split"]
        rec = record_for(rows) | {"id": pid, "pair_id": pid, "split": split, "synthetic_flags": False}
        (OUT / split / f"{pid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        out[(split, rec["outcome"])] += 1
        if rec["outcome"] in ("invite", "reject") and len(flagged[split]) < 2:
            flagged[split].append(pid)
    for split, (p_photo, p_bias) in flagged.items():
        rows = by_pair[p_photo]
        rec = record_for(rows, reader={"mode": "late", "review_reasons": ["reader:low_confidence_or_little_text"]})
        rec |= {"id": f"{p_photo}_photo_flag", "pair_id": p_photo, "split": split, "synthetic_flags": True}
        (OUT / split / f"{rec['id']}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        rows = by_pair[p_bias]
        must = next(r["req_id"] for r in rows if r["kind"] == "must")
        rec = record_for(rows, bias={"review_reasons": ["bias:swap_flip"], "swap": {"ran": True, "changed_must": [must]}})
        rec |= {"id": f"{p_bias}_swap_flag", "pair_id": p_bias, "split": split, "synthetic_flags": True}
        (OUT / split / f"{rec['id']}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        out[(split, "review (flag added)")] += 2
    # T13: a recruiter rejects every review case (review -> human reject): the letter must be written for it
    for split in ("dev", "test"):
        (OUT / f"{split}_human").mkdir(parents=True, exist_ok=True)
        for f in sorted((OUT / split).glob("*.json")):
            rec = json.loads(f.read_text(encoding="utf-8"))
            if rec["outcome"] != "review":
                continue
            rec |= {"id": rec["id"] + "_human_reject", "decided_by": "human", "outcome": "reject",
                    "gate_reasons": rec["gate_reasons"] + ["decided by a recruiter after review: reject"]}
            (OUT / f"{split}_human" / f"{rec['id']}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1),
                                                                     encoding="utf-8")
            out[(split, "human reject")] += 1
    print(dict(out))


if __name__ == "__main__":
    main()
