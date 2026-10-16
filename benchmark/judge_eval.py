"""Evaluate the NLI Judge as an ERROR DETECTOR on saved Matcher predictions (it never changes decisions).

An item is a Matcher error when the validated decision != gold. The Judge flags an item when its verdict is FAIL
(strict) or FAIL/UNCERTAIN (broad). Reported: flag precision/recall/F1, false-positive flag rate on correct items,
false approvals (wrong MET judged PASS), the Judge review rate, detection recall per hard-case tag, AUROC of the
"decision is wrong" score (1 - s(supporting label)), and the expected calibration error (ECE, 10 bins) of
s(supporting label) read as P(decision correct) -- the NLI scores are NOT that probability, ECE measures how far off
they are. UNCERTAIN decisions are out of scope (NOT_APPLICABLE: they always go to human review).

Items: `--run NAME` reads benchmark/results/NAME; `--pred-dir DIR` reads any run directory (config.json +
predictions.jsonl). With `--replay` the saved raw model outputs are re-validated by the CURRENT matcher/validate.py
with the references of the provider that produced them, so the Judge sees exactly what the pipeline Judge sees.

Thresholds: --calibrate RUN picks tau (tau_pass = tau_fail) maximising strict-flag F1 on that run's records,
restricted to train-dev cases (case index % 5 == 0) when the run is on train. Never calibrate on val/test.
`calibrate_two` (used by judge/experiment.py) also picks tau_pass separately with a stated cost.

  python -m benchmark.judge_eval --run lexical-rag-train --judge-dir <dir> --calibrate-only
  python -m benchmark.judge_eval --run qwen3-4b-q4-rag-val --judge-dir <dir> --tau 0.6 --name pretrained
  python -m benchmark.judge_eval --pred-dir rag_opt/results/e2e/lora__gated --replay --judge-dir <id> \
      --revision <sha> --tau-pass 0.8 --tau-fail 0.7 --hypothesis v2 --name xsmall --out <dir>
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from finetune.train_judge import is_dev
from matcher.judge import NLIJudge, precheck
from matcher.schemas import CV, Requirement

from .compare import ROOT
from .run import DATA, read_jsonl

GRID = [round(0.3 + 0.05 * i, 2) for i in range(14)]


def _provider(knowledge):
    """The knowledge provider that produced a saved run (for an exact validator replay)."""
    from matcher.knowledge import GatedKnowledge, NoKnowledge, RagKnowledge

    if knowledge in (None, "none"):
        return NoKnowledge()
    if knowledge == "rag.bm25":
        return RagKnowledge()
    if knowledge.startswith("rag.gated.v1"):
        return GatedKnowledge()
    raise ValueError(f"no replay provider for knowledge {knowledge!r}")


def load_dir(run_dir, replay=False, split_guard=("train", "val")):
    run_dir = Path(run_dir)
    cfg = json.loads((run_dir / "config.json").read_text())
    if cfg["split"] not in split_guard:
        raise ValueError(f"split {cfg['split']!r} not allowed here (test is locked)")
    cases = {c["case_id"]: c for c in read_jsonl(DATA / f"{cfg['split']}.jsonl")}
    recs = read_jsonl(run_dir / "predictions.jsonl")
    if cfg["split"] == "train":
        recs = [r for r in recs if is_dev(r["case_id"])]
    prov = _provider(cfg.get("knowledge")) if replay else None
    items = []
    for r in recs:
        c = cases[r["case_id"]]
        req = Requirement(**next(x for x in c["job"]["requirements"] if x["req_id"] == r["req_id"]))
        cv = CV(**c["cv"])
        if replay:
            from matcher.validate import parse_model_output, validate

            res = validate(parse_model_output(r["raw"]), cv, req, prov.lookup(req, k=cfg.get("k", 3)))
            r = {**r, "decision": res.decision, "basis": res.basis, "evidence": res.evidence,
                 "needs_human_review": res.needs_human_review, "review_reasons": res.review_reasons}
        else:
            res = SimpleNamespace(decision=r["decision"], basis=r["basis"], evidence=r["evidence"],
                                  evidence_spans=r.get("evidence_spans"), review_reasons=r.get("review_reasons", []))
        items.append((r, res, cv, req))
    return cfg, items


def load(run, replay=False):
    return load_dir(ROOT / run, replay=replay)


def pairs_for(judge, items):
    kinds, pairs = [], []
    for _, res, cv, req in items:
        kind, prems = judge.premises(res, cv)
        kinds.append(kind)
        pairs.append([(p, judge.hyp(req)) for p in prems])
    return kinds, pairs


def probs_for(judge, items):
    """NLI probabilities once per item (verdicts for any tau are derived from these). Same premises and hypothesis
    as the pipeline (quote line context, chunked whole CV: NLIJudge.premises / item_probs / hyp)."""
    kinds, pairs = pairs_for(judge, items)
    return list(zip(kinds, judge.item_probs(pairs)))


def verdicts(judge, items, kp, tau=None, tau_pass=None, tau_fail=None):
    judge.tau_pass = tau if tau_pass is None else tau_pass
    judge.tau_fail = tau if tau_fail is None else tau_fail
    return [judge.verdict(res, p, k, precheck(res, cv)[1] if k is not None else [])
            for (_, res, cv, _), (k, p) in zip(items, kp)]


def _prf(flag, err):
    tp = sum(f and e for f, e in zip(flag, err))
    fp = sum(f and not e for f, e in zip(flag, err))
    fn = sum(e and not f for f, e in zip(flag, err))
    p = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": p, "recall": rc, "f1": 2 * p * rc / (p + rc) if p + rc else 0.0,
            "false_positive_flag_rate": fp / max(1, err.count(False)), "flags": tp + fp, "tp": tp, "fp": fp, "fn": fn}


def metrics(items, findings):
    rows = [(r, f) for (r, *_), f in zip(items, findings) if f.judge_verdict != "NOT_APPLICABLE"]
    err = [r["decision"] != r["gold_decision"] for r, _ in rows]
    strict = [f.judge_verdict == "FAIL" for _, f in rows]
    broad = [f.judge_verdict in ("FAIL", "UNCERTAIN") for _, f in rows]
    # wrongness score for AUROC / correctness confidence for ECE (items with NLI scores only)
    conf, cerr = [], []
    for (r, f), e in zip(rows, err):
        if f.nli_probs is None:
            continue
        en, c = f.nli_probs["entailment"], f.nli_probs["contradiction"]
        conf.append(en if r["decision"] == "MET" else (c if f.premise_kind == "quotes" else 1 - en))
        cerr.append(e)
    pos = [1 - c for c, e in zip(conf, cerr) if e]
    neg = [1 - c for c, e in zip(conf, cerr) if not e]
    auroc = (sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg))) if pos and neg else None
    bins = [[] for _ in range(10)]
    for c, e in zip(conf, cerr):
        bins[min(9, int(c * 10))].append((c, not e))
    ece = sum(len(b) * abs(sum(c for c, _ in b) / len(b) - sum(ok for _, ok in b) / len(b)) for b in bins if b) / len(conf) if conf else None
    tags = sorted({t for r, _ in rows for t in r["tags"]})
    per_tag = {}
    for t in tags:
        idx = [i for i, (r, _) in enumerate(rows) if t in r["tags"] and err[i]]
        if idx:
            per_tag[t] = {"errors": len(idx), "detected_strict": sum(strict[i] for i in idx) / len(idx)}
    # false approvals: the Matcher says MET, gold says otherwise, the Judge says PASS
    wrong_met = [(r, f) for (r, *_), f in zip(items, findings) if r["decision"] == "MET" and r["gold_decision"] != "MET"]
    fa = [(r, f) for r, f in wrong_met if f.judge_verdict == "PASS"]
    all_rows = [(r, f) for (r, *_), f in zip(items, findings)]
    judge_review = sum(f.requires_human_review for _, f in all_rows)
    val_review = [bool(r.get("needs_human_review")) for r, _ in all_rows]
    union = sum(v or f.judge_verdict in ("FAIL", "UNCERTAIN") for v, (_, f) in zip(val_review, all_rows))
    return {"n_items": len(all_rows), "n_applicable": len(rows), "n_errors": sum(err), "strict": _prf(strict, err),
            "broad": _prf(broad, err),
            "false_approvals": {"wrong_met": len(wrong_met), "judged_pass": len(fa),
                                "rate": len(fa) / len(wrong_met) if wrong_met else None,
                                "judged_pass_and_no_validator_review": sum(not r.get("needs_human_review") for r, _ in fa),
                                "items": [f"{r['case_id']}/{r['req_id']}" for r, _ in fa]},
            "review_rate": {"judge_recommends_review": judge_review / max(1, len(all_rows)),
                            "validator": sum(val_review) / max(1, len(all_rows)),
                            "validator_or_judge_flag": union / max(1, len(all_rows))},
            "auroc_error_detection": auroc, "ece_correctness": ece, "per_tag_error_detection": per_tag,
            "verdicts": {v: sum(f.judge_verdict == v for f in findings) for v in ("PASS", "FAIL", "UNCERTAIN", "NOT_APPLICABLE")}}


def calibrate_one(judge, items, kp, grid=GRID):
    """Legacy protocol: tau_pass = tau_fail = tau maximising strict-flag F1 (ties -> the lower tau, as before)."""
    scores = {t: metrics(items, verdicts(judge, items, kp, t))["strict"]["f1"] for t in grid}
    return max(scores, key=scores.get), scores


def calibrate_two(judge, items, kp, w_miss=5.0, grid=GRID):
    """tau_fail as in calibrate_one; then tau_pass (>= tau_fail is not required) minimising
    cost = w_miss * (errors judged PASS) + (correct items judged FAIL/UNCERTAIN), ties -> the lower tau_pass.
    w_miss = 5: one unflagged Matcher error is taken to cost as much as five unnecessary reviews (policy choice,
    stated in docs/JUDGE.md; sensitivity reported)."""
    tau_fail, f1 = calibrate_one(judge, items, kp, grid)
    cost = {}
    for tp in grid:
        fs = verdicts(judge, items, kp, tau_pass=tp, tau_fail=tau_fail)
        rows = [(r, f) for (r, *_), f in zip(items, fs) if f.judge_verdict != "NOT_APPLICABLE"]
        miss = sum(f.judge_verdict == "PASS" and r["decision"] != r["gold_decision"] for r, f in rows)
        extra = sum(f.judge_verdict != "PASS" and r["decision"] == r["gold_decision"] for r, f in rows)
        cost[tp] = w_miss * miss + extra
    tau_pass = min(sorted(cost), key=cost.get)
    return {"tau_fail": tau_fail, "tau_pass": tau_pass, "strict_f1_grid": f1, "pass_cost_grid": cost, "w_miss": w_miss}


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run")
    g.add_argument("--pred-dir")
    ap.add_argument("--replay", action="store_true", help="re-validate saved raw outputs with the current validator")
    ap.add_argument("--judge-dir", required=True)
    ap.add_argument("--revision")
    ap.add_argument("--hypothesis", default="v1")
    ap.add_argument("--name", default="judge")
    ap.add_argument("--tau", type=float)
    ap.add_argument("--tau-pass", type=float)
    ap.add_argument("--tau-fail", type=float)
    ap.add_argument("--calibrate-only", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    judge = NLIJudge(a.judge_dir, name=a.name, revision=a.revision, hypothesis_template=a.hypothesis)
    cfg, items = load_dir(a.pred_dir, a.replay) if a.pred_dir else load(a.run, a.replay)
    run = a.run or Path(a.pred_dir).name
    kp = probs_for(judge, items)
    if a.calibrate_only:
        assert cfg["split"] == "train", "calibrate on train-dev only"
        best, scores = calibrate_one(judge, items, kp)
        out = {"run": run, "judge": a.name, "grid_f1": scores, "tau": best}
        print(json.dumps(out))
        Path(ROOT / "judge").mkdir(exist_ok=True)
        (ROOT / "judge" / f"calibration_{a.name}.json").write_text(json.dumps(out, indent=2) + "\n")
        return
    if a.tau_pass is not None or a.tau_fail is not None:
        tp, tf = a.tau_pass, a.tau_fail
    else:
        tau = a.tau if a.tau is not None else json.loads((ROOT / "judge" / f"calibration_{a.name}.json").read_text())["tau"]
        tp = tf = tau
    findings = verdicts(judge, items, kp, tau_pass=tp, tau_fail=tf)
    m = {"run": run, "split": cfg["split"], "replayed_validator": a.replay, "judge": a.name, "judge_dir": a.judge_dir,
         "provenance": judge.provenance(), "tau_pass": tp, "tau_fail": tf, **metrics(items, findings)}
    out = Path(a.out) if a.out else ROOT / "judge" / f"{run}__{a.name}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "judged.jsonl").write_text("".join(json.dumps({"case_id": r["case_id"], "req_id": r["req_id"],
                                                          "decision": r["decision"], "gold": r["gold_decision"],
                                                          "tags": r["tags"], **f.to_dict()}) + "\n"
                                              for (r, *_), f in zip(items, findings)))
    (out / "metrics.json").write_text(json.dumps(m, indent=2) + "\n")
    print(json.dumps({k: m[k] for k in ("run", "judge", "tau_pass", "tau_fail", "n_applicable", "n_errors", "strict",
                                        "false_approvals", "auroc_error_detection", "ece_correctness")}))


if __name__ == "__main__":
    main()
