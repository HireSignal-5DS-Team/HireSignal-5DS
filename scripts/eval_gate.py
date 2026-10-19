r"""T08/T08b Part B: Outcome gate on the 52 pairs (offline, variant-4 rows). Pick on dev, report on test.

Refuses to run while data/labels/gold/summary.json has unchecked rows or pairs (T08 rule).
Judge NLI scores are recomputed for all 364 rows with the rows' final decisions, for hypothesis templates v1 and v2
(cached in <out>/nli_<tpl>.jsonl; T07 thresholds tau_pass 0.05 / tau_fail 0.15), so variant (e) can be compared.

Rule-2 families (T08b): (a) Judge counts as in T08; (b) Judge doubt on a MET must-have counts only if p(MET) < X;
(c) only if the Judge's entailment < Y; (d) never for language / experience with verified years; (e) template v1;
(f) no Judge in the gate. Each family is tuned on dev over pair flags (info | block) x t_invite (x X or Y):
0 false invites (hard), then review rate <= 25%, then fewest false rejects, then fewest reviews;
ties -> the more careful setting (higher t_invite, the Judge counting more), then pair flags info.
The overall choice is the best family on the same dev key; on a tie, the simpler one ((f) first).

Usage: .venv\Scripts\python scripts\eval_gate.py --rows eval\results\2026-10-18_extra_pairs --out eval\results\<date>_outcome_gate\gate
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.judge.judge import REVIEW, NLIJudge, verdict  # noqa: E402
from services.matcher.validate import evidence_years  # noqa: E402
from services.outcome.gate import JUDGE, V, W, decide  # noqa: E402

GOLD = ROOT / "data/labels/gold"
MODEL = ROOT / "models/DeBERTa-v3-base-mnli-fever-anli"
TAUS = (0.05, 0.15)  # T07, chosen on dev
T_GRID = (50, 60, 70, 75, 80, 85, 90, 95, 100)
X_GRID = (0.80, 0.90, 0.95, 0.98, 0.99, 0.995, 0.999)
Y_GRID = (0.01, 0.05, 0.10, 0.20, 0.30, 0.50)
OUTCOMES = ("invite", "review", "reject")
SIMPLICITY = {"f": 0, "d": 1, "b": 2, "c": 3, "a": 4, "e": 5}


def temp_rule(reqs, pair_review):
    """T05 TEMP outcome: any review reason anywhere -> review; else must MISSING -> reject; else score >= 80 -> invite."""
    score = round(100 * sum(W[r["kind"]] * V[r["decision"]] for r in reqs) / sum(W[r["kind"]] for r in reqs))
    if list(pair_review) + [x for r in reqs for x in r["review_reasons"]]:
        return "review"
    if any(r["kind"] == "must" and r["decision"] == "MISSING" for r in reqs):
        return "reject"
    return "invite" if score >= 80 else "review"


def evaluate(pairs, fn):
    res = {pid: fn(p["reqs"][p_tpl], p["pair_review"]) for pid, p in pairs.items() for p_tpl in [p["tpl"]]}
    out = {}
    for sp in ("dev", "test", "all"):
        sel = [pid for pid in pairs if sp == "all" or pairs[pid]["split"] == sp]
        out[sp] = {"n": len(sel),
                   "confusion_gold_x_gate": {g: {o: sum(pairs[p]["gold"] == g and res[p] == o for p in sel) for o in OUTCOMES}
                                             for g in OUTCOMES},
                   "false_invites": sum(res[p] == "invite" and pairs[p]["gold"] != "invite" for p in sel),
                   "false_rejects": sum(res[p] == "reject" and pairs[p]["gold"] != "reject" for p in sel),
                   "invites_found": sum(res[p] == "invite" and pairs[p]["gold"] == "invite" for p in sel),
                   "review_rate": round(sum(res[p] == "review" for p in sel) / len(sel), 3),
                   "agreement": round(sum(res[p] == pairs[p]["gold"] for p in sel) / len(sel), 3)}
    return out, res


def dev_key(m):
    d = m["dev"]
    return (d["false_invites"] > 0, d["review_rate"] > 0.25, d["false_rejects"], d["review_rate"])


def tie_break(kw):
    """Equal dev results: the more careful setting (higher t_invite, the Judge counting more), then pair flags info."""
    return (-kw["t_invite"], -kw.get("judge_met_max_conf", 0), -kw.get("judge_max_support", 0), kw["pair_flags"] != "info")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--device", default="cuda")
    a = ap.parse_args()
    gsum = json.loads((GOLD / "summary.json").read_text(encoding="utf-8"))
    unchecked = gsum["row_sources"].get("unchecked", 0) + gsum.get("pair_sources", {}).get("unchecked", 0)
    if unchecked:
        sys.exit(f"gold not final: {unchecked} unchecked rows/pairs in data/labels/gold/summary.json - not tuning (T08 rule)")
    src, out = Path(a.rows), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(line) for line in open(src / "rows_all_52_variant4.jsonl", encoding="utf-8")]
    profiles = json.loads((src / "profiles_all_52.json").read_text(encoding="utf-8"))
    gold = {p["pair_id"]: p for p in csv.DictReader(open(GOLD / "pairs_gold.csv", encoding="utf-8"))}

    # NLI per template on the final decisions (premise depends on decision, basis and quotes)
    nli = {}
    for tpl in ("v1", "v2"):
        cache = out / f"nli_{tpl}.jsonl"
        if not cache.exists():
            j = NLIJudge(MODEL, *TAUS, device=a.device, template=tpl)
            items = [(profiles[r["pair_id"]]["profile"]["anonymised_text"], {"text": r["requirement"], "min_years": r["min_years"]},
                      {"decision": r["pred"], "basis": r["basis"], "evidence": r["quotes"], "review_reasons": r["review_reasons"]})
                     for r in rows]
            sc = [x for i in range(0, len(items), 16) for x in j.score_many(items[i:i + 16])]
            cache.write_text("".join(json.dumps({"kind": k, "probs": p}) + "\n" for k, p, _ in sc), encoding="utf-8")
        nli[tpl] = [json.loads(line) for line in open(cache, encoding="utf-8")]

    def gate_rows(tpl):
        out_rows = []
        for r, n in zip(rows, nli[tpl]):
            m = {"decision": r["pred"], "basis": r["basis"]}
            v, _ = verdict(m, n["kind"], n["probs"], *TAUS)
            reasons = [x for x in r["review_reasons"] if x not in JUDGE] + ([REVIEW[v]] if v in REVIEW else [])
            quotes = [q["quote"] for q in r["quotes"]]
            out_rows.append({"pair_id": r["pair_id"], "req_id": r["req_id"], "kind": r["kind"], "category": r["category"],
                             "decision": r["pred"], "review_reasons": reasons, "info_flags": r.get("info_flags") or [],
                             "confidence": (r.get("confidence") or {}).get("normalized"),
                             "judge": {"verdict": v, "nli_probs": n["probs"]}, "min_years": r["min_years"],
                             "evidence_years": evidence_years(quotes) if r["min_years"] and quotes else None})
        return out_rows

    by_tpl = {tpl: gate_rows(tpl) for tpl in ("v1", "v2")}
    sanity = sum(x["judge"]["verdict"] == (r.get("judge_verdict") or "NOT_APPLICABLE")
                 for x, r in zip(by_tpl["v2"], rows))
    pairs = {}
    for pid in sorted(gold, key=lambda x: int(x[1:])):
        pr = profiles[pid]
        pairs[pid] = {"split": gold[pid]["split"], "gold": gold[pid]["gold_outcome"], "tpl": "v2",
                      "pair_review": pr["reader"]["review_reasons"] + pr["profile"]["review_reasons"],
                      "reqs": {tpl: [x for x in by_tpl[tpl] if x["pair_id"] == pid] for tpl in by_tpl}}

    def run(tpl, **kw):
        for p in pairs.values():
            p["tpl"] = tpl
        return evaluate(pairs, lambda q, pr: decide(q, pr, **kw).outcome)

    configs = {"a": [], "b": [], "c": [], "d": [], "e": [], "f": []}
    for t in T_GRID:
        for pf in ("info", "block"):
            base = {"t_invite": t, "pair_flags": pf}
            configs["a"].append(("v2", base))
            configs["b"] += [("v2", base | {"judge_met_max_conf": x}) for x in X_GRID]
            configs["c"] += [("v2", base | {"judge_max_support": y}) for y in Y_GRID]
            configs["d"].append(("v2", base | {"judge_skip_proven": True}))
            configs["e"].append(("v1", base))
            configs["f"].append(("v2", base | {"judge": "none"}))
    results, best = {}, {}
    for fam, cfgs in configs.items():
        scored = []
        for tpl, kw in cfgs:
            m, res = run(tpl, **kw)
            scored.append({"template": tpl, "settings": kw, "metrics": m, "per_pair": res})
        results[fam] = scored
        best[fam] = min(scored, key=lambda x: (dev_key(x["metrics"]), tie_break(x["settings"])))
    for p in pairs.values():
        p["tpl"] = "v2"
    temp_m, _ = evaluate(pairs, lambda q, pr: temp_rule(q, pr))
    chosen = min(best, key=lambda f: (dev_key(best[f]["metrics"]), SIMPLICITY[f]))
    summary = {"label": "Matcher + Judge rows real-GPU; NLI recomputed real-GPU" if a.device == "cuda" else "real-CPU",
               "gold_summary": {k: gsum[k] for k in ("pairs", "gold_outcomes", "outcomes_by_split", "row_sources", "pair_sources")},
               "judge_v2_recomputed_equals_saved_verdicts": f"{sanity}/{len(rows)}",
               "temp_rule": temp_m, "best_per_family": {f: {k: best[f][k] for k in ("template", "settings", "metrics", "per_pair")}
                                                        for f in best},
               "chosen_family": chosen, "chosen": {k: best[chosen][k] for k in ("template", "settings", "metrics", "per_pair")}}
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    (out / "all_configs.json").write_text(json.dumps({f: [{k: x[k] for k in ("template", "settings", "metrics")} for x in v]
                                                      for f, v in results.items()}, indent=1), encoding="utf-8")
    print("sanity v2 verdicts equal:", summary["judge_v2_recomputed_equals_saved_verdicts"])
    print("TEMP", {sp: {k: temp_m[sp][k] for k in ("false_invites", "false_rejects", "invites_found", "review_rate")} for sp in ("dev", "test")})
    for f in best:
        m = best[f]["metrics"]
        print(f, best[f]["template"], best[f]["settings"],
              {sp: {k: m[sp][k] for k in ("false_invites", "false_rejects", "invites_found", "review_rate", "agreement")} for sp in ("dev", "test")})
    print("chosen:", chosen)


if __name__ == "__main__":
    main()
