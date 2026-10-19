r"""T08 Part A: one combined rows file for all 52 pairs (variant 4 = confidence check + Judge) and the Matcher metrics.

Inputs:
  eval/results/2026-10-18_judge_confidence/rows_4_both.jsonl   T07 variant 4 for the 40 first pairs (offline Judge/conf)
  <out>/j2r6_nice/rows.jsonl   the 10 J2 r6 rows re-run through the station API with kind = nice (Approver decision)
  <out>/new12/rows.jsonl       the 12 new pairs through /match (with confidence) + /judge
Gold, kind and split are always read from the current data/labels/gold/requirements_gold.csv.
Also re-reports T07's confidence threshold on the 40 first pairs with J2 r6 = nice (dev table).

Usage: .venv\Scripts\python scripts\eval_extra_pairs.py --out eval\results\2026-10-18_extra_pairs
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from eval_real import metrics  # noqa: E402

T06 = ROOT / "eval/results/2026-10-18_real_baseline"
T07 = ROOT / "eval/results/2026-10-18_judge_confidence"
GOLD = ROOT / "data/labels/gold"
GRID = (0.60, 0.65, 0.70, 0.72, 0.75, 0.80, 0.85, 0.90, 0.95)


def load(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def pre_confidence(r):
    """The decision before the confidence rule (station rows have it applied; it only fires on a non-UNCERTAIN
    decision, which the validator left equal to the model decision, so the model decision is the one before)."""
    return r["model_decision"] if "match:low_confidence" in r["review_reasons"] else r["pred"]


def conf_variant(rows, tau):
    out = []
    for r in rows:
        base = pre_confidence(r)
        p = ((r.get("confidence") or {}).get("normalized") or {}).get(r["model_decision"]) if r["model_decision"] else None
        out.append(r | {"pred": "UNCERTAIN" if (p is not None and p < tau and base != "UNCERTAIN") else base})
    return out


def report(rows):
    m = metrics(rows)
    unc = [r for r in rows if r["gold"] == "UNCERTAIN"]
    return {k: m[k] for k in ("n", "accuracy", "macro_f1", "f1_per_class", "false_met", "confusion_gold_x_pred")} | {
        "uncertain_recall": round(sum(r["pred"] == "UNCERTAIN" for r in unc) / max(1, len(unc)), 3),
        "review_load": round(sum(bool(r["review_reasons"]) for r in rows) / len(rows), 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    gold = {(g["pair_id"], g["req_id"]): g for g in csv.DictReader(open(GOLD / "requirements_gold.csv", encoding="utf-8"))}
    old = {(r["pair_id"], r["req_id"]): r for r in load(T07 / "rows_4_both.jsonl")}
    for r in load(out / "j2r6_nice/rows.jsonl"):
        old[(r["pair_id"], r["req_id"])] = r  # re-run with kind = nice
    rows = list(old.values()) + load(out / "new12/rows.jsonl")
    changed_gold = []
    for r in rows:
        g = gold[(r["pair_id"], r["req_id"])]
        if r["gold"] != g["gold_decision"]:
            changed_gold.append(f"{r['pair_id']} {r['req_id']}: {r['gold']} -> {g['gold_decision']}")
        r.update(gold=g["gold_decision"], kind=g["kind"], split=g["split"], gold_source=g["source"])
    assert len(rows) == len(gold) == 364, (len(rows), len(gold))
    rows.sort(key=lambda r: (int(r["pair_id"][1:]), int(r["req_id"][1:])))
    (out / "rows_all_52_variant4.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                                   encoding="utf-8")
    profiles = json.loads((T06 / "profiles.json").read_text(encoding="utf-8"))
    profiles |= json.loads((out / "new12/profiles.json").read_text(encoding="utf-8"))
    (out / "profiles_all_52.json").write_text(json.dumps(profiles, indent=1, ensure_ascii=False), encoding="utf-8")

    new = [r for r in rows if int(r["pair_id"][1:]) > 40]
    first40 = [r for r in rows if int(r["pair_id"][1:]) <= 40]
    sel = lambda rs, sp: [r for r in rs if sp == "all" or r["split"] == sp]  # noqa: E731
    summary = {"label": "real-GPU (Matcher + Judge); 12 new pairs: gold rows unchecked = AI pre-labels (provisional)",
               "gold_changes_vs_saved_rows": changed_gold,
               "unchecked_gold_rows": sum(r["gold_source"] == "unchecked" for r in rows),
               "matcher_variant4": {"new_12": {sp: report(sel(new, sp)) for sp in ("dev", "test", "all")},
                                    "all_52": {sp: report(sel(rows, sp)) for sp in ("dev", "test", "all")}}}
    # T07 re-report with J2 r6 = nice: tau_conf table on the 40 first pairs (their gold rows are all checked)
    dev40 = sel(first40, "dev")
    table = [{"tau_conf": t, "dev_macro_f1": metrics(conf_variant(dev40, t))["macro_f1"],
              "dev_accuracy": metrics(conf_variant(dev40, t))["accuracy"]} for t in GRID]
    base = metrics([r | {"pred": pre_confidence(r)} for r in dev40])
    summary["t07_rereport_j2r6_nice"] = {"dev_baseline_macro_f1": base["macro_f1"], "table": table,
                                         "best": max(table, key=lambda x: x["dev_macro_f1"]),
                                         "test_at_0.72": report(conf_variant(sel(first40, "test"), 0.72)),
                                         "test_baseline": report([r | {"pred": pre_confidence(r)} for r in sel(first40, "test")])}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    for k in ("new_12", "all_52"):
        for sp in ("dev", "test", "all"):
            m = summary["matcher_variant4"][k][sp]
            print(f"{k} {sp}: n {m['n']} acc {m['accuracy']} mF1 {m['macro_f1']} F1 {m['f1_per_class']} falseMET {m['false_met']} "
                  f"UNCrec {m['uncertain_recall']} load {m['review_load']}")
    print("T07 re-report:", summary["t07_rereport_j2r6_nice"]["dev_baseline_macro_f1"], table, "gold changes:", changed_gold)


if __name__ == "__main__":
    main()
