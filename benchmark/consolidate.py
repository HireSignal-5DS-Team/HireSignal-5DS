"""One consolidated table over every run of a split, adding to metrics.json:
UNCERTAIN rate (final and raw) and two deterministic explanation-quality proxies computed from the raw answers:
  expl_present  = parsed answer whose explanation has >= 5 words
  expl_on_topic = parsed answer whose explanation names a requirement skill term (or the quoted CV text)
These are proxies, not human ratings.

  python -m benchmark.consolidate --split val      -> benchmark/results/CONSOLIDATED_val.md (+ .json)
"""
import argparse
import json
from pathlib import Path

from matcher.validate import parse_model_output

from .run import DATA, read_jsonl

ROOT = Path(__file__).resolve().parents[1] / "benchmark/results"


def explanation_proxies(recs, terms):
    present = on_topic = 0
    for r in recs:
        a = parse_model_output(r["raw"])
        if not a:
            continue
        words = a.explanation.split()
        present += len(words) >= 5
        low = a.explanation.casefold()
        on_topic += any(t.casefold() in low for t in terms[(r["case_id"], r["req_id"])]) or \
            any(q.strip() and q.strip().casefold() in low for q in a.evidence)
    n = len(recs)
    return present / n, on_topic / n


def rows(split, root=ROOT):
    cases = read_jsonl(DATA / f"{split}.jsonl")
    terms = {(c["case_id"], r["req_id"]): r["skill_terms"] for c in cases for r in c["job"]["requirements"]}
    out = []
    for d in sorted(root.iterdir()):
        if not (d / "metrics.json").exists():
            continue
        cfg, m = json.loads((d / "config.json").read_text()), json.loads((d / "metrics.json").read_text())
        if cfg["split"] != split or cfg.get("limit"):
            continue
        recs = read_jsonl(d / "predictions.jsonl")
        b = cfg["backend"]
        ep, eo = explanation_proxies(recs, terms)
        out.append({
            "run": d.name, "backend": b["backend"], "model": b.get("model_id") or b.get("label") or b["backend"],
            "adapter": b.get("adapter_id"), "n_params": b.get("n_params"), "is_model": b.get("is_model", False),
            "knowledge": cfg["knowledge"], "n": m["n"],
            "macro_f1": m["final"]["macro_f1"], "macro_f1_raw": m["raw_model"]["macro_f1"],
            "false_met": m["final"]["false_met_rate"], "false_met_raw": m["raw_model"]["false_met_rate"],
            "met_precision": m["final"]["per_class"]["MET"]["precision"], "met_recall": m["final"]["per_class"]["MET"]["recall"],
            "json_valid": m["json_schema_validity"], "quote_valid": m["evidence"]["raw_quote_validity"],
            "attribution": m["evidence"]["attribution_vs_gold"],
            "uncertain_rate": sum(r["decision"] == "UNCERTAIN" for r in recs) / len(recs),
            "uncertain_rate_raw": sum(r["model_decision"] == "UNCERTAIN" for r in recs) / len(recs),
            "expl_present": ep, "expl_on_topic": eo, "review_rate": m["needs_human_review_rate"],
            "p50_s": m["latency_s"]["p50"], "p95_s": m["latency_s"]["p95"], "peak_rss_mb": m.get("peak_rss_mb"),
            "hardware": cfg["hardware"].get("gpu") or f"{cfg['hardware'].get('cpu_count')} CPU"})
    return out


def markdown(rs, split):
    f = lambda x, p=3: "n/a" if x is None else (f"{x:.{p}f}" if isinstance(x, float) else str(x))  # noqa: E731
    cols = [("run", "run"), ("model", "model"), ("adapter", "adapter"), ("n_params", "params"), ("macro_f1", "macro-F1"),
            ("macro_f1_raw", "macro-F1 raw"), ("false_met", "false-MET"), ("false_met_raw", "false-MET raw"),
            ("met_precision", "MET P"), ("met_recall", "MET R"), ("json_valid", "JSON valid"), ("quote_valid", "quote valid"),
            ("attribution", "evidence attribution"), ("uncertain_rate", "UNCERTAIN rate"), ("uncertain_rate_raw", "UNCERTAIN raw"),
            ("expl_present", "expl. present"), ("expl_on_topic", "expl. on topic"), ("review_rate", "review rate"),
            ("p50_s", "p50 s"), ("p95_s", "p95 s"), ("peak_rss_mb", "RSS MB")]
    lines = [f"# Consolidated Matcher comparison — split `{split}`", "",
             "final = after deterministic validation; raw = the model's own decision. Gold UNCERTAIN share: "
             f"{GOLD_UNC.get(split, 'n/a')}. Explanation columns are deterministic proxies, not human ratings.", "",
             "| " + " | ".join(h for _, h in cols) + " |", "|" + "---|" * len(cols)]
    for r in sorted(rs, key=lambda r: -r["macro_f1"]):
        lines.append("| " + " | ".join(f(r[k], 2 if k in ("p50_s", "p95_s") else 3) if k != "n_params"
                                        else (f"{r[k]:,}" if r[k] else "0 (no model)" if not r["is_model"] else "n/a")
                                        for k, _ in cols) + " |")
    return "\n".join(lines) + "\n"


GOLD_UNC = {}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="val")
    a = ap.parse_args()
    golds = [g for c in read_jsonl(DATA / f"{a.split}.jsonl") for g in c["gold"].values()]
    GOLD_UNC[a.split] = f"{sum(g['decision'] == 'UNCERTAIN' for g in golds) / len(golds):.3f}"
    rs = rows(a.split)
    (ROOT / f"CONSOLIDATED_{a.split}.json").write_text(json.dumps(rs, indent=2) + "\n")
    md = markdown(rs, a.split)
    (ROOT / f"CONSOLIDATED_{a.split}.md").write_text(md)
    print(md)
