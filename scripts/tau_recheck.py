r"""T09b: offline re-check of the Matcher confidence threshold tau_conf on the V6 rows (no llama-server, no Judge run).

Rule (services/matcher/matcher.py apply_confidence_rule): p(model decision) < tau -> UNCERTAIN + match:low_confidence,
p = the renormalised label probability (confidence.normalized). The saved V6 rows were made with tau = 0.72, so:
- tau >= 0.72 is exact: rows newly turned UNCERTAIN lose their Judge reasons (the Judge returns NOT_APPLICABLE on
  UNCERTAIN);
- tau < 0.72 turns some rows back to the model decision, but the Judge never ran on them (it saw UNCERTAIN). Their
  verdict is unknown, so the gate is computed twice: bound A = Judge silent, bound B = Judge `judge:disagrees`.
Choice on dev only: 0 false invites, review rate <= 25%, fewest false rejects, highest macro-F1. 0.72 is kept unless
another value has strictly fewer false rejects (or meets the 25% review cap where 0.72 does not) under BOTH bounds.
Test is reported once, for 0.72 and the chosen value.

Usage: .venv\Scripts\python scripts\tau_recheck.py --out eval\results\2026-10-18_tau_recheck
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from eval_rag_matcher import EXTRA, GATE, GOLD, report  # noqa: E402

ROWS = ROOT / "eval/results/2026-10-18_rag_matcher/rows_V6.jsonl"
SAVED_TAU = 0.72
LOW = "match:low_confidence"
JUDGE = ("judge:disagrees", "judge:uncertain")


def p_model(r):
    return ((r.get("confidence") or {}).get("normalized") or {}).get(r["model_decision"]) if r["model_decision"] else None


def at_tau(r, tau, bound):
    """The row as /match + /judge would have given it with this tau (bound: 'A' Judge silent, 'B' Judge disagrees,
    used only where the Judge verdict is unknown)."""
    flipped = LOW in r["review_reasons"]  # flipped by tau 0.72: the decision before the rule is the model decision
    d0 = r["model_decision"] if flipped else r["pred"]
    reasons = [x for x in r["review_reasons"] if x != LOW]
    p = p_model(r)
    if p is not None and p < tau and d0 != "UNCERTAIN":
        return r | {"pred": "UNCERTAIN", "review_reasons": [x for x in reasons if x not in JUDGE] + [LOW],
                    "judge": {"verdict": "NOT_APPLICABLE"}}
    if flipped:  # back to the model decision; the Judge never saw it
        judge = ({"verdict": "PASS"}, []) if bound == "A" else ({"verdict": "FAIL"}, ["judge:disagrees"])
        return r | {"pred": d0, "review_reasons": reasons + judge[1], "judge": judge[0], "judge_unknown": True}
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(x) for x in open(ROWS, encoding="utf-8")]
    profiles = json.loads((EXTRA / "profiles_all_52.json").read_text(encoding="utf-8"))
    gold_pairs = {p["pair_id"]: p for p in csv.DictReader(open(GOLD / "pairs_gold.csv", encoding="utf-8"))}
    dev = [r for r in rows if r["split"] == "dev"]

    # parity: tau 0.72 must give back the saved rows exactly
    key = lambda r: (r["pred"], sorted(r["review_reasons"]))  # noqa: E731  (what metrics + gate read)
    assert all(key(at_tau(r, SAVED_TAU, b)) == key(r) for r in rows for b in "AB")

    taus = [round(0.50 + 0.02 * i, 2) for i in range(21)]
    sweep = []
    for tau in taus:
        line = {"tau": tau}
        for b in "AB":
            res = report([at_tau(r, tau, b) for r in rows], profiles, gold_pairs)["dev"]  # report() needs both splits
            line |= {f"{b}_false_invites": res["gate"]["false_invites"], f"{b}_false_rejects": res["gate"]["false_rejects"],
                     f"{b}_review_rate": res["gate"]["review_rate"], f"{b}_macro_f1": res["macro_f1"]}
        line["dev_rows_judge_unknown"] = sum(LOW in r["review_reasons"] and not (p_model(r) < tau) for r in dev)
        line["dev_uncertain_by_rule"] = sum(at_tau(r, tau, "A")["pred"] == "UNCERTAIN" and LOW in at_tau(r, tau, "A")["review_reasons"]
                                            for r in dev)
        sweep.append(line)
    with open(out / "sweep.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(sweep[0]))
        w.writeheader()
        w.writerows(sweep)

    def ok(x, b):
        return x[f"{b}_false_invites"] == 0 and x[f"{b}_review_rate"] <= 0.25

    base = next(x for x in sweep if x["tau"] == SAVED_TAU)
    better = [x for x in sweep if x["tau"] != SAVED_TAU and all(ok(x, b) for b in "AB") and all(
        (not ok(base, b)) or x[f"{b}_false_rejects"] < base[f"{b}_false_rejects"] for b in "AB")]
    chosen = min(better, key=lambda x: (max(x["A_false_rejects"], x["B_false_rejects"]),
                                        -min(x["A_macro_f1"], x["B_macro_f1"]), abs(x["tau"] - SAVED_TAU)))["tau"] if better else SAVED_TAU

    test = {}
    for tau in sorted({SAVED_TAU, chosen}):
        test[str(tau)] = {b: {k: v for k, v in report([at_tau(r, tau, b) for r in rows], profiles, gold_pairs)["test"].items()
                              if k in ("macro_f1", "f1_per_class", "false_met", "uncertain_recall", "gate")} for b in "AB"}
    summary = {"label": "offline, from real-GPU V6 rows (eval/results/2026-10-18_rag_matcher/rows_V6.jsonl)",
               "rule": "p = confidence.normalized[model_decision] < tau -> UNCERTAIN (services/matcher/matcher.py)",
               "gate_settings": GATE, "taus": taus,
               "bounds": "A = Judge silent, B = Judge judge:disagrees, on rows whose Judge verdict is unknown (tau < 0.72)",
               "dev_at_0.72": base, "strictly_better_on_dev": [x["tau"] for x in better], "chosen_on_dev": chosen,
               "test_once": test}
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    for x in sweep:
        print(x)
    print("strictly better:", [x["tau"] for x in better], "chosen:", chosen)
    print(json.dumps(test))


if __name__ == "__main__":
    main()
