"""Paired test of the human-review rate between E2E arms (same 202 requirements; saved LIVE raw outputs, no model).

    python -m rag_opt.review_rate --root rag_opt/results/e2e --model lora [--label v1] [--out stem]

Each arm's raw outputs are replayed through the CURRENT matcher/validate.py with the arm's own references
(rag_opt/replay_validator.replay), so run it once per validator version (v2: from a checkout that has validator v2).
Per pair: review rate of each arm, exact McNemar on the paired review flags, paired bootstrap 95% CI of the rate
difference (2,000 resamples, seed 0), and the review-reason counts that differ most.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from matcher.knowledge import GatedKnowledge, NoKnowledge, RagKnowledge  # noqa: E402
from matcher.schemas import CV, Requirement  # noqa: E402
from matcher.validate import parse_model_output, validate  # noqa: E402
from rag.significance import mcnemar_exact  # noqa: E402

PROVIDERS = {"none": NoKnowledge, "bm25": RagKnowledge, "gated": GatedKnowledge}


def flags(run_dir, arm, cases, providers):
    prov = providers[arm.removesuffix("-repeat")]
    out = {}
    for p in map(json.loads, (Path(run_dir) / "predictions.jsonl").read_text().splitlines()):
        c = cases[p["case_id"]]
        req = Requirement(**next(r for r in c["job"]["requirements"] if r["req_id"] == p["req_id"]))
        res = validate(parse_model_output(p["raw"]), CV(**c["cv"]), req, prov.lookup(req, k=3))
        out[(p["case_id"], p["req_id"])] = (res.needs_human_review, tuple(res.review_reasons),
                                             res.decision == p["gold_decision"])
    return out


def compare(base, cand, keys, n_boot=2000, seed=0):
    import numpy as np

    b = np.array([base[k][0] for k in keys], float)
    c = np.array([cand[k][0] for k in keys], float)
    x, y, p = mcnemar_exact(b.astype(bool), c.astype(bool))  # x: reviewed only in base, y: only in cand
    rng = np.random.default_rng(seed)
    d = [float((c[s] - b[s]).mean()) for s in (rng.integers(0, len(keys), len(keys)) for _ in range(n_boot))]
    rb = Counter(r for k in keys for r in base[k][1])
    rc = Counter(r for k in keys for r in cand[k][1])
    diff = sorted(((rc[r] - rb[r], r) for r in set(rb) | set(rc)), key=lambda t: -abs(t[0]))[:4]
    # reviews avoided on items the arm gets right vs wrong (review load that matters)
    saved_ok = sum(base[k][0] and not cand[k][0] and cand[k][2] for k in keys)
    saved_wrong = sum(base[k][0] and not cand[k][0] and not cand[k][2] for k in keys)
    return {"rate_base": round(b.mean(), 4), "rate_cand": round(c.mean(), 4), "delta": round(float(c.mean() - b.mean()), 4),
            "ci95": [round(float(np.percentile(d, 2.5)), 4), round(float(np.percentile(d, 97.5)), 4)],
            "reviewed_only_base": x, "reviewed_only_cand": y, "mcnemar_p": round(p, 4),
            "review_dropped_and_correct": saved_ok, "review_dropped_and_wrong": saved_wrong,
            "reason_count_changes": {r: v for v, r in diff}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="rag_opt/results/e2e")
    ap.add_argument("--model", default="lora")
    ap.add_argument("--label", default="current validator")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    cases = {c["case_id"]: c for c in map(json.loads, (ROOT / "benchmark/data/val.jsonl").read_text().splitlines())}
    providers = {k: v() for k, v in PROVIDERS.items()}
    arms = {}
    for d in sorted(Path(a.root).iterdir()):
        if d.name.startswith(a.model + "__") and (d / "predictions.jsonl").exists():
            arm = d.name.split("__", 1)[1]
            if arm.removesuffix("-repeat") in providers:
                arms[arm] = flags(d, arm, cases, providers)
    keys = sorted(set.intersection(*[set(v) for v in arms.values()]))
    pairs = [(c, "none") for c in arms if c != "none" and "none" in arms]
    if "none-repeat" in arms:
        pairs += [(c, "none-repeat") for c in ("gated", "bm25") if c in arms]
    res = {"label": a.label, "model": a.model, "n": len(keys), "pairs": {f"{c} vs {b}": compare(arms[b], arms[c], keys)
                                                                        for c, b in pairs}}
    L = [f"# Review-rate comparison ({a.model}, {a.label}; saved LIVE raw outputs replayed, no model call)", "",
         "| comparison | review rate base → cand | Δ | 95% CI | reviewed only base / only cand | McNemar p | dropped reviews: correct / wrong |",
         "|---|---|---|---|---|---|---|"]
    for name, r in res["pairs"].items():
        L.append(f"| {name} | {r['rate_base']:.3f} → {r['rate_cand']:.3f} | {r['delta']:+.3f} | [{r['ci95'][0]:+.3f}, "
                 f"{r['ci95'][1]:+.3f}] | {r['reviewed_only_base']} / {r['reviewed_only_cand']} | {r['mcnemar_p']} | "
                 f"{r['review_dropped_and_correct']} / {r['review_dropped_and_wrong']} |")
    L += ["", "Largest review-reason count changes (cand − base):", ""]
    L += [f"- {name}: {r['reason_count_changes']}" for name, r in res["pairs"].items()]
    md = "\n".join(L) + "\n"
    if a.out:
        Path(f"{a.out}.md").write_text(md)
        Path(f"{a.out}.json").write_text(json.dumps(res, indent=1) + "\n")
    print(md)
    return res


if __name__ == "__main__":
    main()
