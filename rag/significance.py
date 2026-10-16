"""Paired significance tests.

Library functions (used by rag_opt/ and rag/integration/compare_matcher.py style comparisons):
- mcnemar_exact(a_correct, b_correct): exact two-sided McNemar test on paired per-item correctness.
- macro_f1(gold, pred): macro-F1 over MET/MISSING/UNCERTAIN; None predictions count as wrong for every class
  (same rule as benchmark/metrics.py).
- paired_bootstrap_diff(gold, base, cand): paired bootstrap 95% CI of macro-F1(cand) - macro-F1(base)
  (2,000 resamples, seed 0, as in rag/integration/compare_matcher.py).

Run as a script, it reproduces the exact McNemar tests on Hit@1 reported in docs/EVALUATION.md
(reads eval/results/results.csv):  python rag/significance.py
"""
from math import comb
from pathlib import Path

LABELS = ("MET", "MISSING", "UNCERTAIN")


def mcnemar_exact(a_correct, b_correct):
    """Return (a_only, b_only, p) for two equally long sequences of booleans (same items, same order)."""
    a_only = sum(bool(a) and not bool(b) for a, b in zip(a_correct, b_correct, strict=True))
    b_only = sum(bool(b) and not bool(a) for a, b in zip(a_correct, b_correct, strict=True))
    n = a_only + b_only
    p = min(1.0, 2 * sum(comb(n, k) for k in range(min(a_only, b_only) + 1)) / 2 ** n) if n else 1.0
    return a_only, b_only, p


def macro_f1(gold, pred, labels=LABELS):
    f = []
    for c in labels:
        tp = sum(g == c and p == c for g, p in zip(gold, pred))
        fp = sum(g != c and p == c for g, p in zip(gold, pred))
        fn = sum(g == c and p != c for g, p in zip(gold, pred))
        f.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return sum(f) / len(f)


def paired_bootstrap_diff(gold, base, cand, n_boot=2000, seed=0, metric=macro_f1):
    """(point difference, (low, high)) of metric(cand) - metric(base) with a paired percentile bootstrap."""
    import numpy as np

    gold, base, cand = list(gold), list(base), list(cand)
    n = len(gold)
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n_boot):
        s = rng.integers(0, n, n)
        g = [gold[i] for i in s]
        diffs.append(metric(g, [cand[i] for i in s]) - metric(g, [base[i] for i in s]))
    return metric(gold, cand) - metric(gold, base), (float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5)))


PAIRS = [  # (strategy, model, mode, setting) A vs B
    (("fixed", "bge-m3", "dense", "global"), ("structure", "bge-m3", "dense", "global")),
    (("fixed", "bge-m3", "dense", "scoped"), ("structure", "bge-m3", "dense", "scoped")),
    (("fixed", "e5-small", "dense", "global"), ("structure", "e5-small", "dense", "global")),
    (("fixed", "e5-small", "hybrid", "scoped"), ("structure", "e5-small", "hybrid", "scoped")),
    (("fixed", "-", "bm25", "scoped"), ("structure", "-", "bm25", "scoped")),
    (("structure", "e5-small", "dense", "global"), ("structure", "bge-m3", "dense", "global")),
    (("structure", "e5-small", "dense", "scoped"), ("structure", "bge-m3", "dense", "scoped")),
]


def main():
    import pandas as pd

    df = pd.read_csv(Path(__file__).parent / "eval/results/results.csv")
    df = df[df.type != "none"].assign(h1=lambda d: d.first_hit_rank == 1)

    def hits(strategy, model, mode, setting):
        sel = (df.strategy == strategy) & (df.model == model) & (df["mode"] == mode) & (df.setting == setting)
        return df[sel].set_index("qid").h1

    for a, b in PAIRS:
        ha, hb = hits(*a), hits(*b)
        a_only, b_only = int((ha & ~hb).sum()), int((~ha & hb).sum())
        n = a_only + b_only
        p = min(1.0, 2 * sum(comb(n, k) for k in range(min(a_only, b_only) + 1)) / 2 ** n) if n else 1.0
        print(f"{'/'.join(a)} vs {'/'.join(b)}: A-only={a_only} B-only={b_only} p={p:.3f}")


if __name__ == "__main__":
    main()
