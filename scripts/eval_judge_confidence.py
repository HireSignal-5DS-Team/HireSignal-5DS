r"""T07: Judge (NLI) + confidence check on the saved T06 Matcher rows (no Matcher re-run).

1. Regenerate the anonymised CV text of each pair from the private Reader output (same anonymiser code, rules only),
   compare it with the text the Matcher saw (T06 profiles.json) and check every saved quote span.
2. NLI scores for every row (DeBERTa-v3-base-mnli-fever-anli, cached in nli_scores.jsonl).
3. On DEV only: tau_conf (max dev macro-F1); hypothesis template + tau_pass / tau_fail (max dev F1 of "Judge flag ->
   wrong row", with the Judge flagging at most 25% of the judged dev rows).
4. Ablation (baseline / +confidence / +Judge / +both) on dev, test, all, and without J2 r6; TEMP outcome rule.

Usage: .venv\Scripts\python scripts\eval_judge_confidence.py --out eval\results\<date>_judge_confidence [--device cuda]
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from eval_real import metrics, temp_outcome  # noqa: E402
from services.judge.judge import REVIEW, NLIJudge, verdict  # noqa: E402
from services.profile import anonymise_cv  # noqa: E402

T06 = ROOT / "eval/results/2026-10-18_real_baseline"
MODEL = ROOT / "models/DeBERTa-v3-base-mnli-fever-anli"
CONF_GRID = [round(0.50 + 0.01 * i, 2) for i in range(50)]
CONF_TABLE = (0.80, 0.85, 0.90, 0.95, 0.98)
TAU_GRID = [round(0.05 * i, 2) for i in range(1, 20)]
TEMPLATES = ("v1", "v2")
JUDGE_LOAD_CAP = 0.25  # Judge flags at most 25% of the judged dev rows (Locked target: review rate <= 25%)


def as_match(r):
    return {"decision": r["pred"], "basis": r["basis"], "evidence": r["quotes"], "review_reasons": r["review_reasons"]}


def p_model(r):
    c = r["confidence"] or {}
    return (c.get("normalized") or {}).get(r["model_decision"]) if r["model_decision"] else None


def apply_conf(r, tau):
    """The /match confidence rule: p(model decision) < tau -> UNCERTAIN + match:low_confidence."""
    p = p_model(r)
    if tau is None or p is None or p >= tau or r["pred"] == "UNCERTAIN":
        return r["pred"], []
    return "UNCERTAIN", ["match:low_confidence"]


def variant(rows, nli, tau_conf, taus):
    """Rows with the variant's decision and review reasons. taus=None: no Judge."""
    out = []
    for r, (kind, probs, _) in zip(rows, nli):
        pred, extra = apply_conf(r, tau_conf)
        jv = None
        if taus is not None:
            m = as_match(r) | {"decision": pred}
            # a decision made UNCERTAIN by the confidence rule is not judged (as in production: /judge after /match)
            jv, _ = verdict(m, None if pred == "UNCERTAIN" else kind, probs, *taus)
            extra = extra + ([REVIEW[jv]] if jv in REVIEW else [])
        out.append(r | {"pred": pred, "review_reasons": r["review_reasons"] + extra, "judge_verdict": jv})
    return out


def report(rows):
    m = metrics(rows)
    unc = [r for r in rows if r["gold"] == "UNCERTAIN"]
    wrong = [r for r in rows if r["gold"] != r["pred"]]
    return {"accuracy": m["accuracy"], "macro_f1": m["macro_f1"], "f1_per_class": m["f1_per_class"],
            "false_met": m["false_met"], "uncertain_recall": round(sum(r["pred"] == "UNCERTAIN" for r in unc) / max(1, len(unc)), 3),
            "review_load": round(sum(bool(r["review_reasons"]) for r in rows) / len(rows), 3),
            "errors_flagged_for_review": f"{sum(bool(r['review_reasons']) for r in wrong)}/{len(wrong)}",
            "confusion_gold_x_pred": m["confusion_gold_x_pred"], "n": m["n"]}


def outcomes(rows, profiles, gold_pairs):
    res = []
    for pid in sorted(profiles):
        o, s, _ = temp_outcome([r for r in rows if r["pair_id"] == pid], profiles[pid])
        res.append((gold_pairs[pid]["split"], gold_pairs[pid]["gold_outcome"], o))
    out = {}
    for sp in ("dev", "test", "all"):
        sel = [x for x in res if sp == "all" or x[0] == sp]
        out[sp] = {"agreement": round(sum(g == o for _, g, o in sel) / len(sel), 3),
                   "review_rate": round(sum(o == "review" for *_, o in sel) / len(sel), 3),
                   "reject_rate": round(sum(o == "reject" for *_, o in sel) / len(sel), 3)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--device", default="cuda")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(line) for line in open(T06 / "rows.jsonl", encoding="utf-8")]
    profiles = json.loads((T06 / "profiles.json").read_text(encoding="utf-8"))
    gold_pairs = {p["pair_id"]: p for p in csv.DictReader(open(ROOT / "data/labels/gold/pairs_gold.csv", encoding="utf-8"))}

    # 1. regenerate the anonymised texts and check the saved quote spans
    regen = {"pairs": 0, "text_identical": 0, "quotes": 0, "quote_spans_ok_saved": 0, "quote_spans_ok_regen": 0, "mismatches": []}
    texts = {}
    for pid, p in profiles.items():
        reader = json.loads((ROOT / "private" / f"{p['reader']['cv_id']}.reader.json").read_text(encoding="utf-8"))
        new = anonymise_cv(reader["text"], cv_id=p["reader"]["cv_id"], sections=reader.get("sections")).text
        saved = p["profile"]["anonymised_text"]
        regen["pairs"] += 1
        regen["text_identical"] += new == saved
        texts[pid] = new
        for r in (r for r in rows if r["pair_id"] == pid):
            for e in r["quotes"]:
                regen["quotes"] += 1
                regen["quote_spans_ok_saved"] += saved[e["start"]:e["end"]] == e["quote"]
                ok = new[e["start"]:e["end"]] == e["quote"]
                regen["quote_spans_ok_regen"] += ok
                if not ok:
                    regen["mismatches"].append(f"{pid} {r['req_id']}")
    print("regen:", {k: v for k, v in regen.items() if k != "mismatches"}, regen["mismatches"][:5], flush=True)

    # 2. NLI scores per hypothesis template (cached)
    nli_by = {}
    for tpl in TEMPLATES:
        cache = out / f"nli_scores_{tpl}.jsonl"
        if not cache.exists():
            judge = NLIJudge(MODEL, tau_pass=0.5, tau_fail=0.5, device=a.device, template=tpl)
            t = time.perf_counter()
            items = [(texts[r["pair_id"]], {"text": r["requirement"], "min_years": r["min_years"]}, as_match(r)) for r in rows]
            scored = []
            for i in range(0, len(items), 16):
                scored += judge.score_many(items[i:i + 16])
            secs = round(time.perf_counter() - t, 1)
            with open(cache, "w", encoding="utf-8") as f:
                for r, (kind, probs, notes) in zip(rows, scored):
                    f.write(json.dumps({"pair_id": r["pair_id"], "req_id": r["req_id"], "kind": kind, "probs": probs,
                                        "notes": notes}) + "\n")
            (out / f"nli_timing_{tpl}.json").write_text(json.dumps({"rows": len(rows), "seconds": secs, "device": a.device,
                                                                     "label": "real-GPU" if a.device == "cuda" else "real-CPU"}))
            print(f"NLI {tpl}: scored {len(rows)} rows in {secs}s on {a.device}", flush=True)
        nli_by[tpl] = [(d["kind"], d["probs"], d["notes"]) for d in map(json.loads, open(cache, encoding="utf-8"))]

    dev = [i for i, r in enumerate(rows) if r["split"] == "dev"]
    sel = lambda rs, idx: [rs[i] for i in idx]  # noqa: E731
    dev_rows = sel(rows, dev)
    dev_nli = sel(nli_by["v2"], dev)  # the confidence rule does not use NLI

    # 3a. tau_conf on dev: max macro-F1 (ties -> lower review load, then higher tau)
    conf_table = []
    for tau in sorted(set(CONF_GRID) | set(CONF_TABLE)):
        v = variant(dev_rows, dev_nli, tau, None)
        wrong_before = [r for r in dev_rows if r["gold"] != r["pred"]]
        changed = [x for x, r in zip(v, dev_rows) if x["pred"] != r["pred"]]
        conf_table.append({"tau_conf": tau, "dev_macro_f1": metrics(v)["macro_f1"], "dev_accuracy": metrics(v)["accuracy"],
                           "made_uncertain": len(changed),
                           "errors_caught": sum(r["gold"] != r["pred"] for r in changed),  # were wrong before
                           "now_correct": sum(x["pred"] == x["gold"] for x in changed),
                           "correct_sent_to_review": sum(r["gold"] == r["pred"] for r in changed),
                           "dev_errors_before": len(wrong_before)})
    base_f1 = metrics(dev_rows)["macro_f1"]
    best_conf = max(conf_table, key=lambda x: (x["dev_macro_f1"], -x["made_uncertain"], x["tau_conf"]))
    tau_conf = best_conf["tau_conf"] if best_conf["dev_macro_f1"] > base_f1 else None

    # 3b. Judge template + taus on dev: max F1 of "flag (FAIL or UNCERTAIN) -> the row is wrong" over judged rows,
    #     with flags <= JUDGE_LOAD_CAP of the judged dev rows; ties -> fewer flags, then higher tau_fail
    judge_table = []
    for tpl in TEMPLATES:
        dn = sel(nli_by[tpl], dev)
        for tp in TAU_GRID:
            for tf in TAU_GRID:
                v = variant(dev_rows, dn, None, (tp, tf))
                judged = [x for x in v if x["judge_verdict"] not in (None, "NOT_APPLICABLE")]
                flag = [x for x in judged if x["judge_verdict"] in ("FAIL", "UNCERTAIN")]
                tp_ = sum(x["gold"] != x["pred"] for x in flag)
                wrong = sum(x["gold"] != x["pred"] for x in judged)
                prec, rec = (tp_ / len(flag) if flag else 0.0), (tp_ / wrong if wrong else 0.0)
                judge_table.append({"template": tpl, "tau_pass": tp, "tau_fail": tf, "flagged": len(flag),
                                    "flag_share": round(len(flag) / len(judged), 3), "errors_flagged": tp_,
                                    "flag_precision": round(prec, 3), "flag_recall": round(rec, 3),
                                    "f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0,
                                    "judged": len(judged), "wrong_judged": wrong})
    ok = [x for x in judge_table if x["flag_share"] <= JUDGE_LOAD_CAP]
    best_judge = max(ok, key=lambda x: (x["f1"], -x["flagged"], x["tau_fail"]))
    best_unconstrained = max(judge_table, key=lambda x: (x["f1"], -x["flagged"]))
    taus = (best_judge["tau_pass"], best_judge["tau_fail"])
    nli = nli_by[best_judge["template"]]

    # 4. ablation
    variants = {"1_baseline": (None, None), "2_confidence": (tau_conf, None), "3_judge": (None, taus), "4_both": (tau_conf, taus)}
    abl, abl_wo, toc = {}, {}, {}
    for name, (tc, tj) in variants.items():
        v = variant(rows, nli, tc, tj)
        (out / f"rows_{name}.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in v), encoding="utf-8")
        abl[name] = {sp: report([x for x in v if sp == "all" or x["split"] == sp]) for sp in ("dev", "test", "all")}
        wo = [x for x in v if not (x["job"] == "J2" and x["req_id"] == "r6")]
        abl_wo[name] = {sp: report([x for x in wo if sp == "all" or x["split"] == sp]) for sp in ("dev", "test", "all")}
        toc[name] = outcomes(v, profiles, gold_pairs)
    summary = {"label": "Matcher rows: real-GPU (T06). NLI: " + ("real-GPU" if a.device == "cuda" else "real-CPU"),
               "regeneration_check": regen, "tau_conf": tau_conf, "tau_conf_choice": best_conf, "dev_macro_f1_baseline": base_f1,
               "confidence_table_dev": conf_table, "judge_taus": {"tau_pass": taus[0], "tau_fail": taus[1]},
               "judge_template": best_judge["template"], "judge_choice": best_judge,
               "judge_best_without_load_cap": best_unconstrained, "judge_load_cap": JUDGE_LOAD_CAP,
               "judge_table_dev": judge_table, "ablation": abl,
               "ablation_without_J2_r6": abl_wo, "temp_outcome_PROVISIONAL": toc,
               "verdict_counts_all": {k: sum(x[0] == k for x in nli) for k in ("quotes", "cv", "none", None)}}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print("tau_conf", tau_conf, best_conf, "| judge", taus, best_judge)
    for name in variants:
        for sp in ("dev", "test"):
            x = abl[name][sp]
            print(f"{name:13s} {sp:4s} acc {x['accuracy']} mF1 {x['macro_f1']} F1 {x['f1_per_class']} falseMET {x['false_met']} "
                  f"UNCrec {x['uncertain_recall']} load {x['review_load']} errs_flagged {x['errors_flagged_for_review']} "
                  f"outcome {toc[name][sp]}")


if __name__ == "__main__":
    main()
