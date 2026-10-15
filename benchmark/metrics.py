"""Benchmark metrics (pure Python). Input: prediction records as written by benchmark/run.py:
{"case_id", "req_id", "gold": {decision, basis, evidence, tags}, "result": RequirementResult dict,
 "raw": str, "parsed": bool, "latency_s": float}
and a {case_id: cv_text} map (needed for verbatim-quote checks and evidence overlap).
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from matcher.validate import parse_model_output  # noqa: E402

CLASSES = ("MET", "MISSING", "UNCERTAIN")
INVALID = "INVALID"  # raw model output that could not be parsed


def _div(a, b):
    return a / b if b else None


def classification(gold, pred):
    """gold, pred: equal-length label lists. pred may contain INVALID (always wrong, counted in confusion)."""
    n = len(gold)
    conf = {g: Counter() for g in CLASSES}
    for g, p in zip(gold, pred):
        conf[g][p] += 1
    per_class = {}
    for c in CLASSES:
        tp = conf[c][c]
        fp = sum(conf[g][c] for g in CLASSES if g != c)
        fn = sum(conf[c].values()) - tp
        p, r = _div(tp, tp + fp), _div(tp, tp + fn)
        f1 = 2 * p * r / (p + r) if p and r else 0.0
        per_class[c] = {"precision": p, "recall": r, "f1": f1, "support": tp + fn}
    non_met = sum(g != "MET" for g in gold)
    return {
        "n": n,
        "accuracy": _div(sum(g == p for g, p in zip(gold, pred)), n),
        "macro_f1": sum(per_class[c]["f1"] for c in CLASSES) / len(CLASSES),
        "per_class": per_class,
        "confusion": {g: {p: conf[g][p] for p in (*CLASSES, INVALID) if conf[g][p] or p != INVALID} for g in CLASSES},
        "false_met_rate": _div(sum(p == "MET" and g != "MET" for g, p in zip(gold, pred)), non_met),
        "uncertain_recall": per_class["UNCERTAIN"]["recall"],
        "predicted_uncertain_share": _div(sum(p == "UNCERTAIN" for p in pred), n),
    }


def _overlaps(text, gold_quotes, pred_spans):
    gold_spans = [(i, i + len(q)) for q in gold_quotes for i in _all_find(text, q)]
    return any(a < d and c < b for a, b in pred_spans for c, d in gold_spans)


def _all_find(text, q):
    i = text.find(q)
    while q and i >= 0:
        yield i
        i = text.find(q, i + 1)


def compute(records, cv_texts):
    if not records:
        return {"n": 0}
    gold = [r["gold"]["decision"] for r in records]
    final = [r["result"]["decision"] for r in records]
    raw_dec = [r["result"]["model_decision"] or INVALID for r in records]
    out = {"final": classification(gold, final), "raw_model": classification(gold, raw_dec)}

    # unsupported MET: final MET whose evidence is empty or not verbatim in the CV
    out["final"]["unsupported_met"] = sum(
        r["result"]["decision"] == "MET" and (not r["result"]["evidence"] or
                                             any(q not in cv_texts[r["case_id"]] for q in r["result"]["evidence"]))
        for r in records)

    # raw output quality
    n_quotes = n_verbatim = 0
    for r in records:
        ans = parse_model_output(r["raw"])
        if ans:
            for q in ans.evidence:
                n_quotes += 1
                n_verbatim += bool(q.strip()) and q.strip() in cv_texts[r["case_id"]]
    out["raw_model"]["json_validity"] = _div(sum(bool(r["parsed"]) for r in records), len(records))
    out["raw_model"]["quotes_emitted"] = n_quotes
    out["raw_model"]["quote_verbatim_rate"] = _div(n_verbatim, n_quotes)

    # per tag accuracy (final decision)
    tag_hits = defaultdict(lambda: [0, 0])
    for r, g, p in zip(records, gold, final):
        for t in r["gold"]["tags"]:
            tag_hits[t][0] += g == p
            tag_hits[t][1] += 1
    out["per_tag"] = {t: {"n": n, "accuracy": h / n} for t, (h, n) in sorted(tag_hits.items())}

    # evidence overlap for gold MET
    met = [r for r in records if r["gold"]["decision"] == "MET"]
    out["evidence_overlap_gold_met"] = _div(
        sum(_overlaps(cv_texts[r["case_id"]], r["gold"]["evidence"], [tuple(s) for s in r["result"]["evidence_spans"]])
            for r in met), len(met))

    # basis agreement on items where gold and prediction are both MISSING
    both_missing = [r for r in records if r["gold"]["decision"] == r["result"]["decision"] == "MISSING"]
    out["missing_basis_accuracy"] = _div(sum(r["gold"]["basis"] == r["result"]["basis"] for r in both_missing),
                                         len(both_missing))

    lat = [r["latency_s"] for r in records]
    out["latency"] = {"mean_s": sum(lat) / len(lat), "max_s": max(lat), "total_s": sum(lat)}
    out["n"] = len(records)
    return out
