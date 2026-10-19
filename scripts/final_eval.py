r"""T13 Part B: final evaluation report from the n8n e2e runs (scripts/n8n_e2e.py --cards) of the full production
chain on the test pairs (+ the 5 labelled photo / scan cases). Nothing is tuned here.

Reads <out>/<run>_result.json + <run>_execution.json; gold from data/labels/gold/. Writes <out>/final_summary.json.
Usage: .venv\Scripts\python scripts\final_eval.py --out eval\results\2026-10-19_final_eval
"""
import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data/labels/gold"
LABELS = ("MET", "MISSING", "UNCERTAIN")
OUTCOMES = ("invite", "review", "reject")
STATIONS = {"reader": ["HTTP /reader"], "profile": ["HTTP /profile"], "job card": ["Job card", "HTTP /job"],
            "rag": ["RAG lookup"], "match": ["HTTP /match"], "judge": ["HTTP /judge"], "bias": ["Bias Auditor"],
            "outcome": ["HTTP /outcome"], "report": ["Report Writer"]}


def f1s(pairs):
    out = {}
    for lab in LABELS:
        tp = sum(g == lab and p == lab for g, p in pairs)
        fp = sum(g != lab and p == lab for g, p in pairs)
        fn = sum(g == lab and p != lab for g, p in pairs)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        out[lab] = round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0
    return out


def block(rows):
    """rows: [{pair, outcome, gold_outcome, reqs [(gold, pred)], report_source, report_flags, bias, wall_s, stations}]"""
    pairs = [x for r in rows for x in r["reqs"]]
    per = f1s(pairs)
    conf = {g: {p: sum(r["gold_outcome"] == g and r["outcome"] == p for r in rows) for p in OUTCOMES} for g in OUTCOMES}
    st = defaultdict(list)
    for r in rows:
        for k, v in r["stations"].items():
            st[k].append(v)
    return {
        "pairs": len(rows), "requirements": len(pairs),
        "req_accuracy": round(sum(g == p for g, p in pairs) / max(1, len(pairs)), 3),
        "req_macro_f1": round(statistics.mean(per.values()), 3), "req_f1": per,
        "false_met": sum(p == "MET" and g != "MET" for g, p in pairs),
        "outcome_confusion_gold_rows_pred_cols": conf,
        "outcome_agreement": sum(r["outcome"] == r["gold_outcome"] for r in rows),
        "false_invites": sum(r["outcome"] == "invite" and r["gold_outcome"] != "invite" for r in rows),
        "false_rejects": sum(r["outcome"] == "reject" and r["gold_outcome"] != "reject" for r in rows),
        "review_rate": round(sum(r["outcome"] == "review" for r in rows) / max(1, len(rows)), 3),
        "report_llm": sum(r["report_source"] == "llm" for r in rows),
        "report_template_fallback": sum(r["report_source"] == "template" for r in rows),
        "bias_swap_ran": sum(bool((r["bias"].get("swap") or {}).get("ran")) for r in rows),
        "bias_swap_flips": sum("bias:swap_flip" in (r["bias"].get("review_reasons") or []) for r in rows),
        "bias_swap_identical_input": sum(bool((r["bias"].get("swap") or {}).get("identical_matcher_input")) for r in rows),
        "latency_s_per_cv_mean": round(statistics.mean(r["wall_s"] for r in rows), 1) if rows else None,
        "latency_s_per_cv_max": round(max(r["wall_s"] for r in rows), 1) if rows else None,
        "station_s_mean": {k: round(statistics.mean(v), 2) for k, v in st.items()},
        "station_s_max": {k: round(max(v), 2) for k, v in st.items()},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    gold_pairs = {p["pair_id"]: p for p in csv.DictReader(open(GOLD / "pairs_gold.csv", encoding="utf-8"))}
    gold_req = defaultdict(dict)
    for r in csv.DictReader(open(GOLD / "requirements_gold.csv", encoding="utf-8")):
        gold_req[r["pair_id"]][r["req_id"]] = r["gold_decision"]
    groups = {"test pairs (original files)": [], "photo / scan cases": []}
    for p in sorted(out.glob("*_execution.json")):
        e = json.loads(p.read_text(encoding="utf-8"))
        res = json.loads((out / p.name.replace("_execution", "_result")).read_text(encoding="utf-8"))
        pid = e["pair"]
        stations = {k: round(sum(t["ms"] or 0 for n in names for t in e["node_timings"].get(n, [])) / 1000, 2)
                    for k, names in STATIONS.items()}
        row = {"run": e["run"], "pair": pid, "outcome": res["outcome"], "gold_outcome": gold_pairs[pid]["gold_outcome"],
               "reqs": [(gold_req[pid][q["req_id"]], q["decision"]) for q in res["requirements"] if q["req_id"] in gold_req[pid]],
               "report_source": (res.get("report") or {}).get("source"),
               "report_flags": (res.get("report") or {}).get("info_flags"), "bias": res.get("bias") or {},
               "reader": res.get("reader") or {}, "wall_s": e["total_wall_s"], "stations": stations,
               "identity_found": e["checks"]["identity_values_found_in_execution_data"],
               "raw_text_in_execution": e["checks"]["raw_cv_text_in_execution_data"]}
        groups["photo / scan cases" if "cv_file" in e else "test pairs (original files)"].append(row)
    summary = {"label": "real-GPU, full production chain through n8n (Reader late fusion, Profile + guard, confirmed "
                        "cards, RAG V6, Matcher + confidence, Judge, Bias Auditor, gate, Report Writer v3)",
               "groups": {k: block(v) for k, v in groups.items() if v},
               "privacy": {"identity_values_found": sum(r["identity_found"] for v in groups.values() for r in v),
                           "raw_text_in_execution": sum(bool(r["raw_text_in_execution"]) for v in groups.values() for r in v)},
               "rows": {k: [{x: r[x] for x in ("run", "pair", "outcome", "gold_outcome", "report_source", "wall_s")}
                            | {"reader_mode": r["reader"].get("mode"), "reader_reasons": r["reader"].get("review_reasons"),
                               "swap": r["bias"].get("swap")} for r in v] for k, v in groups.items()}}
    (out / "final_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    for k, v in summary["groups"].items():
        print("==", k)
        for x, y in v.items():
            print(f"   {x}: {y}")
    print("privacy:", summary["privacy"])


if __name__ == "__main__":
    main()
