"""Validate benchmark data against benchmark/CONTRACT.md. Exit code 1 on any violation.

Usage: python benchmark/check_data.py [--data benchmark/data]
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from matcher.schemas import CV, Job  # noqa: E402
from matcher.validate import CONSISTENT  # noqa: E402

SPLITS = ("train", "val", "test")
TAGS = {"exact", "equivalence", "related_not_equivalent", "experience_years", "ambiguous_duration", "not_documented",
        "negation", "rag_only_term", "certification", "education", "language", "contradictory_requirement"}


def load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def check_case(case, split):
    errs = []
    cid = case.get("case_id", "?")
    if set(case) != {"case_id", "split", "source", "cv", "job", "gold"}:
        errs.append(f"{cid}: top-level keys {sorted(case)}")
        return errs
    if case["split"] != split:
        errs.append(f"{cid}: split field {case['split']!r} != file split {split!r}")
    if case["source"] not in ("handwritten", "generated"):
        errs.append(f"{cid}: bad source {case['source']!r}")
    try:
        cv, job = CV.model_validate(case["cv"]), Job.model_validate(case["job"])
    except Exception as e:  # pydantic ValidationError
        return errs + [f"{cid}: schema error {e}"]
    rids = [r.req_id for r in job.requirements]
    if len(set(rids)) != len(rids):
        errs.append(f"{cid}: duplicate req_id")
    if set(case["gold"]) != set(rids):
        errs.append(f"{cid}: gold keys {sorted(case['gold'])} != requirement ids {sorted(rids)}")
    for rid, g in case["gold"].items():
        where = f"{cid}/{rid}"
        if set(g) != {"decision", "basis", "evidence", "tags"}:
            errs.append(f"{where}: gold keys {sorted(g)}")
            continue
        if g["decision"] not in CONSISTENT or g["basis"] not in CONSISTENT[g["decision"]]:
            errs.append(f"{where}: inconsistent {g['decision']}/{g['basis']}")
        if (g["decision"] == "MET" or g["basis"] == "contradicted") and not g["evidence"]:
            errs.append(f"{where}: {g['decision']}/{g['basis']} needs evidence")
        if g["basis"] == "not_documented" and g["evidence"]:
            errs.append(f"{where}: not_documented must have no evidence")
        for q in g["evidence"]:
            if not q.strip() or q not in cv.text:
                errs.append(f"{where}: evidence not a substring of cv.text: {q!r}")
        if not g["tags"] or set(g["tags"]) - TAGS:
            errs.append(f"{where}: bad tags {g['tags']}")
    return errs


def distribution(cases):
    labels, tags = Counter(), Counter()
    for c in cases:
        for g in c["gold"].values():
            labels[g["decision"] if g["decision"] != "MISSING" else f"MISSING/{g['basis']}"] += 1
            tags.update(g["tags"])
    return labels, tags


def check(data_dir):
    data_dir = Path(data_dir)
    errs, by_split = [], {}
    for split in SPLITS:
        p = data_dir / f"{split}.jsonl"
        if not p.exists():
            errs.append(f"missing file {p}")
            continue
        cases = load(p)
        by_split[split] = cases
        for c in cases:
            errs += check_case(c, split)
    ids = Counter(c["case_id"] for cs in by_split.values() for c in cs)
    errs += [f"duplicate case_id {i}" for i, n in ids.items() if n > 1]
    cv_ids = Counter(c["cv"]["cv_id"] for cs in by_split.values() for c in cs)
    errs += [f"duplicate cv_id {i}" for i, n in cv_ids.items() if n > 1]
    texts = {s: {c["cv"]["text"].strip() for c in cs} for s, cs in by_split.items()}
    for a in texts:
        for b in texts:
            if a < b and texts[a] & texts[b]:
                errs.append(f"{len(texts[a] & texts[b])} CV texts shared between {a} and {b}")
    return errs, by_split


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(Path(__file__).parent / "data"))
    args = ap.parse_args()
    errs, by_split = check(args.data)
    for split, cases in by_split.items():
        labels, tags = distribution(cases)
        n = sum(labels.values())
        print(f"[{split}] cases={len(cases)} requirements={n}")
        print("  labels: " + ", ".join(f"{k}={v} ({v / n:.0%})" for k, v in sorted(labels.items())))
        print("  tags:   " + ", ".join(f"{k}={v}" for k, v in sorted(tags.items())))
    for e in errs[:200]:
        print("ERROR", e)
    print(f"{len(errs)} error(s)")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
