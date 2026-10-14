"""Exact McNemar tests on Hit@1 for the comparisons reported in docs/EVALUATION.md (reads eval/results/results.csv)."""
from math import comb
from pathlib import Path

import pandas as pd

df = pd.read_csv(Path(__file__).parent / "eval/results/results.csv")
df = df[df.type != "none"].assign(h1=lambda d: d.first_hit_rank == 1)
PAIRS = [  # (strategy, model, mode, setting) A vs B
    (("fixed", "bge-m3", "dense", "global"), ("structure", "bge-m3", "dense", "global")),
    (("fixed", "bge-m3", "dense", "scoped"), ("structure", "bge-m3", "dense", "scoped")),
    (("fixed", "e5-small", "dense", "global"), ("structure", "e5-small", "dense", "global")),
    (("fixed", "e5-small", "hybrid", "scoped"), ("structure", "e5-small", "hybrid", "scoped")),
    (("fixed", "-", "bm25", "scoped"), ("structure", "-", "bm25", "scoped")),
    (("structure", "e5-small", "dense", "global"), ("structure", "bge-m3", "dense", "global")),
    (("structure", "e5-small", "dense", "scoped"), ("structure", "bge-m3", "dense", "scoped")),
]


def hits(strategy, model, mode, setting):
    sel = (df.strategy == strategy) & (df.model == model) & (df["mode"] == mode) & (df.setting == setting)
    return df[sel].set_index("qid").h1


for a, b in PAIRS:
    ha, hb = hits(*a), hits(*b)
    a_only, b_only = int((ha & ~hb).sum()), int((~ha & hb).sum())
    n = a_only + b_only
    p = min(1.0, 2 * sum(comb(n, k) for k in range(min(a_only, b_only) + 1)) / 2 ** n) if n else 1.0
    print(f"{'/'.join(a)} vs {'/'.join(b)}: A-only={a_only} B-only={b_only} p={p:.3f}")
