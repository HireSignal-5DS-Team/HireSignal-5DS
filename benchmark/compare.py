"""Comparison table of all runs on one split: python -m benchmark.compare --split val [--out benchmark/results/COMPARISON_val.md]"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "benchmark/results"


def table(split, root=ROOT):
    rows = []
    for d in sorted(root.iterdir()):
        if not (d / "metrics.json").exists():
            continue
        cfg, m = json.loads((d / "config.json").read_text()), json.loads((d / "metrics.json").read_text())
        if cfg["split"] != split or cfg.get("limit"):
            continue
        b = cfg["backend"]
        name = b.get("model_id") or b.get("label") or b["backend"]
        if b.get("adapter_id"):
            name += f" + {b['adapter_id']}"
        if not b.get("is_model") and b["backend"] == "mock":
            name = "MOCK " + name
        f, r, ev = m["final"], m["raw_model"], m["evidence"]
        fmt = lambda x, p=3: "n/a" if x is None else f"{x:.{p}f}"  # noqa: E731
        rows.append(f"| {d.name} | {name} | {cfg['knowledge']} | {m['n']} | {fmt(f['macro_f1'])} | {fmt(r['macro_f1'])} | "
                    f"{fmt(f['false_met_rate'])} | {fmt(r['false_met_rate'])} | {fmt(m['json_schema_validity'])} | "
                    f"{fmt(ev['raw_quote_validity'])} | {fmt(ev['attribution_vs_gold'])} | {fmt(m['needs_human_review_rate'])} | "
                    f"{fmt(m['latency_s']['p50'], 2)} | {fmt(m['latency_s']['p95'], 2)} | {m.get('peak_rss_mb')} | "
                    f"{cfg['hardware'].get('gpu') or str(cfg['hardware'].get('cpu_count')) + ' CPU'} |")
    head = ("| run | model / backend | knowledge | n | macro-F1 final | macro-F1 raw | false-MET final | false-MET raw | "
            "JSON valid | raw quote valid | evidence attribution | review rate | p50 s | p95 s | peak RSS MB | hardware |\n"
            "|" + "---|" * 16)
    return f"# Matcher benchmark — split `{split}`\n\nfinal = after deterministic validation; raw = model decision before it.\n\n" \
           + head + "\n" + "\n".join(rows) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="val")
    ap.add_argument("--out")
    a = ap.parse_args()
    t = table(a.split)
    print(t)
    Path(a.out or ROOT / f"COMPARISON_{a.split}.md").write_text(t)
