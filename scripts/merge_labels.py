r"""Merge the two blind labelling sheets and measure agreement (percent agreement + Cohen's kappa).

Reads data/labels/labelling_sheet_A.xlsx and _B.xlsx (scripts/build_labelling_kit.py). Writes to --out
(default data/labels/merged/): requirements_merged.csv, pairs_merged.csv, agreement.json.
Only rows labelled by BOTH are scored. Each MET quote is checked against the CV file (exact substring).

Usage: .venv\\Scripts\\python scripts\\merge_labels.py [--a FILE] [--b FILE] [--out DIR]
"""
import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import cohen_kappa_score

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "data/labels"
DECISIONS = {"MET", "MISSING", "UNCERTAIN"}
OUTCOMES = {"invite", "review", "reject"}


def norm(v):
    return "" if pd.isna(v) else str(v).strip()


def agreement(a, b, classes):
    """Percent agreement and Cohen's kappa on the rows both labelled; kappa None if undefined (one class only)."""
    both = [(x, y) for x, y in zip(a, b) if x in classes and y in classes]
    if not both:
        return {"n": 0, "percent_agreement": None, "cohen_kappa": None}
    xa, xb = zip(*both)
    agree = sum(x == y for x, y in both) / len(both)
    kappa = None if len(set(xa) | set(xb)) < 2 else round(float(cohen_kappa_score(xa, xb, labels=sorted(classes))), 3)
    return {"n": len(both), "percent_agreement": round(agree, 3), "cohen_kappa": kappa,
            "confusion": {g: {p: sum(x == g and y == p for x, y in both) for p in sorted(classes)} for g in sorted(classes)}}


def merge(a_path, b_path, cv_dir):
    ra, rb = (pd.read_excel(p, sheet_name="requirements") for p in (a_path, b_path))
    pa, pb = (pd.read_excel(p, sheet_name="pairs") for p in (a_path, b_path))
    key = ["pair_id", "job", "cv_file", "req_id"]
    req = ra.merge(rb[key + ["B_decision", "B_cv_quote", "B_notes"]], on=key, how="outer", validate="one_to_one")
    pairs = pa.merge(pb[["pair_id", "B_outcome", "B_reason"]], on="pair_id", how="outer", validate="one_to_one")
    for who in ("A", "B"):
        req[f"{who}_decision"] = req[f"{who}_decision"].map(norm).str.upper()
        pairs[f"{who}_outcome"] = pairs[f"{who}_outcome"].map(norm).str.lower()

    problems = []
    for _, r in req.iterrows():
        cv = (cv_dir / Path(r["cv_file"]).name).read_text(encoding="utf-8")
        for who in ("A", "B"):
            d, q = r[f"{who}_decision"], norm(r[f"{who}_cv_quote"])
            where = f"{r['pair_id']} {r['req_id']} {who}"
            if d and d not in DECISIONS:
                problems.append(f"{where}: unknown decision {d!r}")
            if d == "MET" and not q:
                problems.append(f"{where}: MET without a CV quote")
            if q and q not in cv:
                problems.append(f"{where}: quote is not an exact substring of the CV")
    req["agree"] = req["A_decision"] == req["B_decision"]
    pairs["agree"] = pairs["A_outcome"] == pairs["B_outcome"]
    summary = {"requirements": agreement(req["A_decision"], req["B_decision"], DECISIONS),
               "outcomes": agreement(pairs["A_outcome"], pairs["B_outcome"], OUTCOMES),
               "rows_total": {"requirements": len(req), "pairs": len(pairs)},
               "labelled": {w: {"requirements": int((req[f"{w}_decision"] != "").sum()),
                                "pairs": int((pairs[f"{w}_outcome"] != "").sum())} for w in ("A", "B")},
               "problems": problems}
    return req, pairs, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default=str(LABELS / "labelling_sheet_A.xlsx"))
    ap.add_argument("--b", default=str(LABELS / "labelling_sheet_B.xlsx"))
    ap.add_argument("--cvs", default=str(ROOT / "data/processed/cvs"))
    ap.add_argument("--out", default=str(LABELS / "merged"))
    a = ap.parse_args()
    req, pairs, summary = merge(Path(a.a), Path(a.b), Path(a.cvs))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    req.to_csv(out / "requirements_merged.csv", index=False, encoding="utf-8")
    pairs.to_csv(out / "pairs_merged.csv", index=False, encoding="utf-8")
    (out / "agreement.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "problems"} | {"problems": len(summary["problems"])}, indent=1))


if __name__ == "__main__":
    main()
