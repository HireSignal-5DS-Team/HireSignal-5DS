"""Counterfactual flip analysis across Matcher arms (QA-029: instability vs bias).

Per arm (several run dirs can be combined, e.g. a core-attribute run + a new+placebo run on the same requirements):
- flip rate per attribute with Wilson 95 % CI; placebo (non-protected hobby line) = instability floor;
- protected cells pooled vs placebo cells: Fisher exact test (is the protected flip rate above the floor?);
- borderline vs clear requirements (definition below, fixed before any LoRA result was seen): flip rate per stratum
  and Fisher exact test;
- between two arms: exact McNemar on the shared (requirement, attribute) cells.
Untested cells (both sides invalid output, QA-016) are excluded.

Borderline (model-independent, from bench gold): gold decision UNCERTAIN, or a gold tag in BORDERLINE_TAGS (year
arithmetic, partial or indirect evidence). Clear: every other requirement.

  python -m bias.flip_analysis --arm base=benchmark/results/bias/bias-qwen3-4b-q4,benchmark/results/bias/bias-qwen3-4b-q4-new \
      --arm lora=<core run dir>,benchmark/results/bias/bias-qwen3-4b-q4+hslora-new --out benchmark/results/bias/flip-analysis
"""
import argparse
import json
import math
from pathlib import Path

from matcher.bias_audit import PLACEBO_ATTRIBUTES

from .stats import exact_binom_two_sided, wilson

ROOT = Path(__file__).resolve().parents[1]
BORDERLINE_TAGS = {"ambiguous_duration", "date_range", "sufficient_experience", "insufficient_experience",
                   "partial_evidence", "contradictory_evidence", "implicit_project_evidence"}


def fisher_two_sided(a, b, c, d):
    """Fisher exact test on [[a, b], [c, d]] (rows: groups; columns: flip, no flip)."""
    r1, r2, c1, n = a + b, c + d, a + c, a + b + c + d
    if n == 0:
        return 1.0

    def p(x):
        return math.comb(r1, x) * math.comb(r2, c1 - x) / math.comb(n, c1)
    obs = p(a)
    return min(1.0, sum(p(x) for x in range(max(0, c1 - r2), min(r1, c1) + 1) if p(x) <= obs * (1 + 1e-9)))


def gold_index():
    idx = {}
    for line in (ROOT / "benchmark/data/val.jsonl").read_text().splitlines():
        c = json.loads(line)
        for rid, g in c["gold"].items():
            idx[(c["case_id"], rid)] = g
    return idx


def is_borderline(g):
    return g["decision"] == "UNCERTAIN" or bool(BORDERLINE_TAGS & set(g["tags"]))


def load_cells(dirs):
    """{(case_id, req_id, attr): flip(bool)} over the given run dirs; untested cells are skipped."""
    cells, sources = {}, []
    for d in dirs:
        p = Path(d) / "findings.jsonl"
        recs = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
        sources.append({"dir": str(d), "n_requirements": len(recs)})
        for r in recs:
            for attr, v in r["details"].items():
                if attr == "untested" or not isinstance(v, dict) or v.get("flip") is None:
                    continue
                cells[(r["case_id"], r["req_id"], attr)] = bool(v["flip"])
    return cells, sources


def rate(flags):
    k, n = sum(flags), len(flags)
    return {"flips": k, "n": n, "rate": round(k / n, 4) if n else None, "ci95": wilson(k, n)}


def analyse_arm(cells, gold):
    attrs = sorted({a for _, _, a in cells})
    per_attr = {a: rate([f for (c, r, x), f in cells.items() if x == a]) for a in attrs}
    prot = [f for (c, r, a), f in cells.items() if a not in PLACEBO_ATTRIBUTES]
    plac = [f for (c, r, a), f in cells.items() if a in PLACEBO_ATTRIBUTES]
    out = {"per_attribute": per_attr, "protected_pooled": rate(prot), "placebo": rate(plac)}
    if plac:
        out["protected_vs_placebo_fisher_p"] = fisher_two_sided(sum(prot), len(prot) - sum(prot), sum(plac), len(plac) - sum(plac))
    strata = {}
    for name, want in (("borderline", True), ("clear", False)):
        fl = [f for (c, r, a), f in cells.items() if a not in PLACEBO_ATTRIBUTES and is_borderline(gold[(c, r)]) == want]
        reqs = {(c, r) for (c, r, a) in cells if is_borderline(gold[(c, r)]) == want}
        strata[name] = {**rate(fl), "requirements": len(reqs)}
    b, cl = strata["borderline"], strata["clear"]
    strata["fisher_p"] = fisher_two_sided(b["flips"], b["n"] - b["flips"], cl["flips"], cl["n"] - cl["flips"])
    out["borderline_vs_clear_protected"] = strata
    flipped = sorted({(c, r) for (c, r, a), f in cells.items() if f})
    out["flipped_requirements"] = [{"case_id": c, "req_id": r, "borderline": is_borderline(gold[(c, r)]),
                                    "gold": gold[(c, r)]["decision"], "tags": gold[(c, r)]["tags"],
                                    "attributes": sorted(a for (cc, rr, a), f in cells.items() if f and (cc, rr) == (c, r))}
                                   for c, r in flipped]
    return out


def mcnemar(cells_a, cells_b):
    shared = sorted(set(cells_a) & set(cells_b))
    only_a = sum(cells_a[k] and not cells_b[k] for k in shared)
    only_b = sum(cells_b[k] and not cells_a[k] for k in shared)
    return {"shared_cells": len(shared), "flip_both": sum(cells_a[k] and cells_b[k] for k in shared),
            "flip_only_first": only_a, "flip_only_second": only_b,
            "mcnemar_exact_p": exact_binom_two_sided(only_a, only_a + only_b)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", action="append", required=True, help="name=dir1,dir2,...")
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="LIVE")
    a = ap.parse_args()
    gold = gold_index()
    arms, res = {}, {"label": a.label, "borderline_definition": {"gold_decision": "UNCERTAIN", "tags": sorted(BORDERLINE_TAGS)},
                     "arms": {}}
    for spec in a.arm:
        name, dirs = spec.split("=", 1)
        cells, sources = load_cells(dirs.split(","))
        arms[name] = cells
        res["arms"][name] = {"sources": sources, **analyse_arm(cells, gold)}
    names = list(arms)
    if len(names) == 2:
        res["paired"] = {f"{names[0]}_vs_{names[1]}": mcnemar(arms[names[0]], arms[names[1]])}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "analysis.json").write_text(json.dumps(res, indent=2) + "\n")
    for n, r in res["arms"].items():
        print(n, "protected", r["protected_pooled"], "placebo", r["placebo"], "borderline/clear",
              {k: r["borderline_vs_clear_protected"][k] for k in ("borderline", "clear", "fisher_p")})
    if "paired" in res:
        print(res["paired"])


if __name__ == "__main__":
    main()
