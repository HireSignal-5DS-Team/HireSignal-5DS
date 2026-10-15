"""Benchmark metrics over prediction records (one per requirement, written by benchmark/run.py).

Each record: gold_decision, gold_basis, gold_evidence, tags, decision, basis, model_decision (None = unparseable),
parsed, raw_quotes, raw_quotes_valid, evidence_spans, gold_spans, needs_human_review, latency_s.
"""
import statistics

CLASSES = ("MET", "MISSING", "UNCERTAIN")


def prf(gold, pred):
    out = {}
    for c in CLASSES:
        tp = sum(g == c and p == c for g, p in zip(gold, pred))
        fp = sum(g != c and p == c for g, p in zip(gold, pred))
        fn = sum(g == c and p != c for g, p in zip(gold, pred))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        out[c] = {"precision": prec, "recall": rec, "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
                  "support": tp + fn}
    return out


def decision_metrics(gold, pred):
    """pred may contain None (no parseable answer): it counts as wrong for every class."""
    per = prf(gold, pred)
    non_met = [p for g, p in zip(gold, pred) if g != "MET"]
    return {"macro_f1": sum(per[c]["f1"] for c in CLASSES) / len(CLASSES),
            "accuracy": sum(g == p for g, p in zip(gold, pred)) / len(gold),
            "false_met_rate": sum(p == "MET" for p in non_met) / len(non_met) if non_met else None,
            "per_class": per,
            "confusion": {g: {p: sum(a == g and b == p for a, b in zip(gold, pred)) for p in (*CLASSES, None)}
                          for g in CLASSES}}


def _overlap(spans, gold_spans):
    return any(a < d and c < b for a, b in spans for c, d in gold_spans)


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))] if xs else None


def compute(records):
    gold = [r["gold_decision"] for r in records]
    final = [r["decision"] for r in records]
    raw = [r["model_decision"] for r in records]
    n_quotes = sum(len(r["raw_quotes"]) for r in records)
    raw_met = [r for r in records if r["model_decision"] == "MET"]
    need_ev = [r for r in records if r["gold_basis"] in ("supported", "contradicted") and r["decision"] == r["gold_decision"]]
    tags = sorted({t for r in records for t in r["tags"]})
    lat = [r["latency_s"] for r in records]
    return {
        "n": len(records),
        "final": decision_metrics(gold, final),
        "raw_model": decision_metrics(gold, raw),
        "json_schema_validity": sum(r["parsed"] for r in records) / len(records),
        "basis_accuracy": sum(r["basis"] == r["gold_basis"] for r in records) / len(records),
        "evidence": {
            "raw_quotes": n_quotes,
            "raw_quote_validity": sum(r["raw_quotes_valid"] for r in records) / n_quotes if n_quotes else None,
            "raw_met_with_verified_quote": (sum(r["raw_quotes_valid"] > 0 for r in raw_met) / len(raw_met)) if raw_met else None,
            "attribution_vs_gold": (sum(_overlap(r["evidence_spans"], r["gold_spans"]) for r in need_ev) / len(need_ev))
            if need_ev else None,
            "attribution_n": len(need_ev),
        },
        "validator_changed_decision": sum(r["model_decision"] != r["decision"] for r in records) / len(records),
        "needs_human_review_rate": sum(r["needs_human_review"] for r in records) / len(records),
        "per_tag_accuracy": {t: {"n": sum(t in r["tags"] for r in records),
                                 "accuracy": sum(r["decision"] == r["gold_decision"] for r in records if t in r["tags"])
                                 / sum(t in r["tags"] for r in records)} for t in tags},
        "latency_s": {"mean": statistics.fmean(lat), "p50": pct(lat, 0.5), "p95": pct(lat, 0.95), "max": max(lat)}
        if lat else None,
    }


def to_markdown(m, title):
    f, r = m["final"], m["raw_model"]
    ev = m["evidence"]
    fmt = lambda x: "n/a" if x is None else f"{x:.3f}"  # noqa: E731
    lines = [f"# {title}", "", f"Requirements evaluated: {m['n']}", "",
             "| metric | final (after validation) | raw model output |", "|---|---|---|",
             f"| macro-F1 | {fmt(f['macro_f1'])} | {fmt(r['macro_f1'])} |",
             f"| accuracy | {fmt(f['accuracy'])} | {fmt(r['accuracy'])} |",
             f"| false-MET rate | {fmt(f['false_met_rate'])} | {fmt(r['false_met_rate'])} |",
             *(f"| {c} P / R | {fmt(f['per_class'][c]['precision'])} / {fmt(f['per_class'][c]['recall'])} | "
               f"{fmt(r['per_class'][c]['precision'])} / {fmt(r['per_class'][c]['recall'])} |" for c in CLASSES),
             "", f"- JSON/schema validity: {fmt(m['json_schema_validity'])}",
             f"- basis accuracy (final): {fmt(m['basis_accuracy'])}",
             f"- raw quote validity (exact CV substring): {fmt(ev['raw_quote_validity'])} of {ev['raw_quotes']} quotes",
             f"- raw MET answers with >= 1 verified quote: {fmt(ev['raw_met_with_verified_quote'])}",
             f"- evidence attribution vs gold span (correct MET/contradicted, n={ev['attribution_n']}): {fmt(ev['attribution_vs_gold'])}",
             f"- validator changed the decision: {fmt(m['validator_changed_decision'])}",
             f"- needs human review: {fmt(m['needs_human_review_rate'])}"]
    if m["latency_s"]:
        lat = m["latency_s"]
        lines.append(f"- latency per requirement (s): mean {lat['mean']:.2f}, p50 {lat['p50']:.2f}, p95 {lat['p95']:.2f}")
    lines += ["", "| tag | n | accuracy (final) |", "|---|---|---|",
              *(f"| {t} | {v['n']} | {v['accuracy']:.3f} |" for t, v in m["per_tag_accuracy"].items())]
    return "\n".join(lines) + "\n"
