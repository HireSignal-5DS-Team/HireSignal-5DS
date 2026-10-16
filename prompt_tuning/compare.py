"""Four-arm comparison table + paired statistics against the base arm (same 202 val requirements).

  python -m prompt_tuning.compare --runs base=base-fp16-val lora=lora-fp16-val soft_prompt=sp-base-v1-fp16-val \\
      lora_soft_prompt=sp-lora-v1-fp16-val [--out-root benchmark/results/experimental/soft_prompt]

Paired tests (requirement level, final decision after validation): exact McNemar on correct/incorrect (same formula
as rag/significance.py) and a paired bootstrap 95 % CI of the macro-F1 difference (2000 resamples, seed 13).
Every row carries its label (MEASURED / SMOKE); refuses to mix labels or backends/dtypes in one table.
"""
import argparse
import json
import random
from math import comb
from pathlib import Path

from .common import RESULTS, read_jsonl


def mcnemar(a_ok, b_ok):
    a_only = sum(x and not y for x, y in zip(a_ok, b_ok))
    b_only = sum(y and not x for x, y in zip(a_ok, b_ok))
    n = a_only + b_only
    p = min(1.0, 2 * sum(comb(n, k) for k in range(min(a_only, b_only) + 1)) / 2 ** n) if n else 1.0
    return {"a_only": a_only, "b_only": b_only, "p": p}


def bootstrap_f1_diff(gold, pa, pb, n=2000, seed=13):
    from benchmark.metrics import decision_metrics

    rng, idx, diffs = random.Random(seed), list(range(len(gold))), []
    for _ in range(n):
        s = [rng.choice(idx) for _ in idx]
        g = [gold[i] for i in s]
        diffs.append(decision_metrics(g, [pb[i] for i in s])["macro_f1"] - decision_metrics(g, [pa[i] for i in s])["macro_f1"])
    diffs.sort()
    return {"lo": diffs[int(0.025 * n)], "hi": diffs[int(0.975 * n) - 1]}


def load(out_root, run_id):
    d = Path(out_root) / run_id
    m = json.loads((d / "metrics.json").read_text())
    recs = {(r["case_id"], r["req_id"]): r for r in read_jsonl(d / "predictions.jsonl")}
    return m, recs


def compare(runs, out_root=RESULTS, ref="base"):
    loaded = {arm: load(out_root, rid) for arm, rid in runs.items()}
    labels = {m["label"] for m, _ in loaded.values()}
    setups = {(m["backend"]["dtype"], m["backend"]["device"], m["backend"]["decoding"]["max_new_tokens"])
              for m, _ in loaded.values()}
    if len(labels) > 1:
        raise SystemExit(f"refusing to mix labels in one table: {labels}")
    if len(setups) > 1:
        raise SystemExit(f"refusing an unequal comparison (dtype/device/decoding differ): {setups}")
    keys = sorted(set.intersection(*(set(r) for _, r in loaded.values())))
    ref_m, ref_r = loaded.get(ref, (None, None))
    rows = []
    for arm, (m, r) in loaded.items():
        row = {"arm": arm, "run_id": runs[arm], "label": m["label"], "n": m["n"], "macro_f1": m["final"]["macro_f1"],
               "false_met_rate": m["final"]["false_met_rate"], "json_valid": m["json_schema_validity"],
               "uncertain_rate": m.get("uncertain_rate"), "latency_p50": m["latency_s"]["p50"],
               "latency_p95": m["latency_s"]["p95"], "peak_rss_mb": m["peak_rss_mb"], "peak_vram_mb": m["peak_vram_mb"],
               "config_hash": m["config_hash"][:12],
               "soft_prompt_sha256": ((m["backend"].get("soft_prompt") or {}).get("sha256") or "")[:12] or None}
        if ref_r is not None and arm != ref:
            gold = [ref_r[k]["gold_decision"] for k in keys]
            pa, pb = [ref_r[k]["decision"] for k in keys], [r[k]["decision"] for k in keys]
            row["mcnemar_vs_base"] = mcnemar([x == g for x, g in zip(pa, gold)], [x == g for x, g in zip(pb, gold)])
            row["delta_macro_f1_ci95"] = bootstrap_f1_diff(gold, pa, pb)
        rows.append(row)
    return {"label": labels.pop(), "setup": dict(zip(("dtype", "device", "max_new_tokens"), setups.pop())),
            "n_paired": len(keys), "rows": rows}


def to_markdown(c):
    f = lambda x, d=3: "n/a" if x is None else f"{x:.{d}f}"  # noqa: E731
    lines = [f"# Soft prompt experiment, 4-arm comparison ({c['label']})", "",
             f"Backend: transformers, {c['setup']['dtype']} on {c['setup']['device']}, greedy, max "
             f"{c['setup']['max_new_tokens']} new tokens; {c['n_paired']} paired val requirements.", "",
             "| arm | label | macro-F1 | Δ vs base [95 % CI] | McNemar p | false-MET | JSON valid | UNCERTAIN | "
             "p50 s | p95 s | peak RSS MB | peak VRAM MB | config |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    base = next((r for r in c["rows"] if r["arm"] == "base"), None)
    for r in c["rows"]:
        if "delta_macro_f1_ci95" in r and base:
            ci = r["delta_macro_f1_ci95"]
            delta = f"{r['macro_f1'] - base['macro_f1']:+.3f} [{ci['lo']:+.3f}, {ci['hi']:+.3f}]"
            p = f(r["mcnemar_vs_base"]["p"])
        else:
            delta, p = "ref", "ref"
        lines.append(f"| {r['arm']} | {r['label']} | {f(r['macro_f1'])} | {delta} | {p} | {f(r['false_met_rate'])} | "
                     f"{f(r['json_valid'])} | {f(r['uncertain_rate'])} | {f(r['latency_p50'], 2)} | "
                     f"{f(r['latency_p95'], 2)} | {f(r['peak_rss_mb'], 0)} | {f(r['peak_vram_mb'], 0)} | "
                     f"`{r['config_hash']}` |")
    if c["label"] == "SMOKE":
        lines += ["", "**SMOKE: tiny random model. These numbers check the plumbing only and say nothing about the "
                      "Matcher.**"]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", nargs="+", required=True, help="arm=run_id ...")
    ap.add_argument("--out-root", default=str(RESULTS))
    ap.add_argument("--name", default="COMPARISON")
    a = ap.parse_args(argv)
    c = compare(dict(x.split("=", 1) for x in a.runs), a.out_root)
    out = Path(a.out_root)
    (out / f"{a.name}.json").write_text(json.dumps(c, indent=2) + "\n")
    (out / f"{a.name}.md").write_text(to_markdown(c))
    print(to_markdown(c))
    return c


if __name__ == "__main__":
    main()
