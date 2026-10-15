"""Collect benchmark/results/*/metrics.json into benchmark/results/COMPARISON.md."""
import json
import sys
from pathlib import Path

RESULTS = Path(__file__).parent / "results"


def pct(x):
    return "n/a" if x is None else f"{x:.1%}"


def num(x, d=3):
    return "n/a" if x is None else f"{x:.{d}f}"


def table(results_dir=RESULTS):
    rows = []
    for p in sorted(Path(results_dir).glob("*/metrics.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        meta, m = d["meta"], d["metrics"]
        f, r = m["final"], m["raw_model"]
        rows.append(f"| {p.parent.name} | {meta['split']} | {meta['backend'].get('backend')} | {meta['knowledge']} | "
                    f"{m['n']} | {num(f['macro_f1'])} | {num(f['accuracy'])} | {pct(f['false_met_rate'])} | "
                    f"{num(r['macro_f1'])} | {pct(r['json_validity'])} | {pct(r['quote_verbatim_rate'])} | "
                    f"{num(m['latency']['mean_s'], 3)} | {num(meta['peak_rss_mb'], 0)} |")
    head = ["# Benchmark comparison", "",
            "Final = after deterministic validation; raw = model decision before validation. "
            "Non-model backends (lexical, mock) are references, not SLM results.", "",
            "| arm | split | backend | knowledge | n | macro-F1 | acc | false-MET rate | raw macro-F1 | JSON validity | "
            "quote verbatim | sec/req | peak RSS MB |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    return "\n".join(head + rows) + "\n"


def main():
    results_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else RESULTS
    md = table(results_dir)
    (results_dir / "COMPARISON.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
