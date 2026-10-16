"""Paired comparison of Matcher runs on the same requirements (no model is run).

    MATCHER_DIR=<matcher checkout> python rag/integration/compare_matcher.py BASE_DIR CAND_DIR [...]
Each DIR holds a predictions.jsonl from benchmark.run. Metrics come from the Matcher's own benchmark.metrics.compute
(identical evaluation rules); paired statistics are added here: McNemar on per-requirement correctness and a paired
bootstrap 95% CI (2,000 resamples, seed 0) of the macro-F1 difference.
"""
import json
import os
import sys
from math import comb
from pathlib import Path

import numpy as np

sys.path.insert(0, os.environ["MATCHER_DIR"])
from benchmark import metrics as M  # noqa: E402

LABELS = ["MET", "MISSING", "UNCERTAIN"]


def load(d):
    return {(r["case_id"], r["req_id"]): r for r in map(json.loads, open(Path(d) / "predictions.jsonl", encoding="utf-8"))}


def macro_f1(gold, pred):
    f = []
    for c in LABELS:
        tp = sum(g == c and p == c for g, p in zip(gold, pred))
        fp = sum(g != c and p == c for g, p in zip(gold, pred))
        fn = sum(g == c and p != c for g, p in zip(gold, pred))
        f.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return float(np.mean(f))


def mcnemar(a, b):
    x, y = int((a & ~b).sum()), int((~a & b).sum())
    n = x + y
    return x, y, (min(1.0, 2 * sum(comb(n, k) for k in range(min(x, y) + 1)) / 2 ** n) if n else 1.0)


def main(dirs):
    runs = {Path(d).name: load(d) for d in dirs}
    keys = sorted(set.intersection(*[set(r) for r in runs.values()]))
    base_name = Path(dirs[0]).name
    rows = []
    for name, r in runs.items():
        recs = [r[k] for k in keys]
        m = M.compute(recs)
        f = m["final"]
        rows.append({"run": name, "n": len(recs), "macro-F1": round(f["macro_f1"], 3), "accuracy": round(f["accuracy"], 3),
                     "false-MET": round(f["false_met_rate"], 3), "JSON valid": round(m["json_schema_validity"], 3),
                     "UNCERTAIN rate": round(np.mean([x["decision"] == "UNCERTAIN" for x in recs]), 3),
                     "human review": round(m["needs_human_review_rate"], 3),
                     "latency p50/p95 s": f"{np.percentile([x['latency_s'] for x in recs], 50):.1f}/{np.percentile([x['latency_s'] for x in recs], 95):.1f}",
                     "quote validity": m["evidence"]["raw_quote_validity"] and round(m["evidence"]["raw_quote_validity"], 3),
                     "evidence attribution": m["evidence"]["attribution_vs_gold"] and round(m["evidence"]["attribution_vs_gold"], 3),
                     **{f"{c} P/R": f"{f['per_class'][c]['precision']:.2f}/{f['per_class'][c]['recall']:.2f}" for c in LABELS}})
    gold = [runs[base_name][k]["gold_decision"] for k in keys]
    base = [runs[base_name][k]["decision"] for k in keys]
    stats = []
    rng = np.random.default_rng(0)
    idx = [rng.integers(0, len(keys), len(keys)) for _ in range(2000)]
    for name, r in runs.items():
        if name == base_name:
            continue
        cand = [r[k]["decision"] for k in keys]
        a = np.array([b == g for b, g in zip(base, gold)])
        b = np.array([c == g for c, g in zip(cand, gold)])
        x, y, p = mcnemar(a, b)
        d = [macro_f1([gold[i] for i in s], [cand[i] for i in s]) - macro_f1([gold[i] for i in s], [base[i] for i in s]) for s in idx]
        stats.append({"comparison": f"{name} vs {base_name}", "base-only correct": x, "cand-only correct": y, "McNemar p": round(p, 3),
                      "macro-F1 diff": round(macro_f1(gold, cand) - macro_f1(gold, base), 3),
                      "95% CI": f"[{np.percentile(d, 2.5):+.3f}, {np.percentile(d, 97.5):+.3f}]"})
        for tag in ("equivalent_skill_alias", "rag_suggests_absent_skill", "certification"):
            ks = [i for i, k in enumerate(keys) if tag in runs[base_name][k]["tags"]]
            stats[-1][f"acc {tag} base→cand"] = f"{np.mean([a[i] for i in ks]):.2f}→{np.mean([b[i] for i in ks]):.2f} (n={len(ks)})"
    import pandas as pd
    md = "### Runs\n\n" + pd.DataFrame(rows).to_markdown(index=False) + "\n\n### Paired comparisons\n\n" + pd.DataFrame(stats).to_markdown(index=False) + "\n"
    print(md)
    return md


if __name__ == "__main__":
    main(sys.argv[1:])
