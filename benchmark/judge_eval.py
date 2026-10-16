"""Evaluate the NLI Judge as an ERROR DETECTOR on saved Matcher predictions (it never changes decisions).

An item is a Matcher error when the validated decision != gold. The Judge flags an item when its verdict is FAIL
(strict) or FAIL/UNCERTAIN (broad). Reported: flag precision/recall/F1, false-positive flag rate on correct items,
detection recall per hard-case tag, AUROC of the "decision is wrong" score (1 - p(supporting label)), and the
expected calibration error (ECE, 10 bins) of p(supporting label) as P(decision correct). UNCERTAIN decisions are
out of scope (NOT_APPLICABLE: they always go to human review).

Thresholds: --calibrate RUN picks tau (tau_pass = tau_fail) maximising strict-flag F1 on that run's records,
restricted to train-dev cases (case index % 5 == 0) when the run is on train. Never calibrate on val/test.

  python -m benchmark.judge_eval --run lexical-rag-train --judge-dir <dir> --calibrate-only
  python -m benchmark.judge_eval --run qwen3-4b-q4-rag-val --judge-dir <dir> --tau 0.6 --name pretrained
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from finetune.train_judge import is_dev
from matcher.judge import NLIJudge
from matcher.schemas import CV, Requirement

from .compare import ROOT
from .run import DATA, read_jsonl


def load(run):
    cfg = json.loads((ROOT / run / "config.json").read_text())
    cases = {c["case_id"]: c for c in read_jsonl(DATA / f"{cfg['split']}.jsonl")}
    recs = read_jsonl(ROOT / run / "predictions.jsonl")
    if cfg["split"] == "train":
        recs = [r for r in recs if is_dev(r["case_id"])]
    items = []
    for r in recs:
        c = cases[r["case_id"]]
        req = Requirement(**next(x for x in c["job"]["requirements"] if x["req_id"] == r["req_id"]))
        res = SimpleNamespace(decision=r["decision"], basis=r["basis"], evidence=r["evidence"])
        items.append((r, res, CV(**c["cv"]), req))
    return cfg, items


def probs_for(judge, items):
    """NLI probabilities once per item (verdicts for any tau are derived from these). Same premises as the pipeline
    (quote line context, chunked whole CV: NLIJudge.premises / item_probs)."""
    from matcher.judge import hypothesis

    kinds, pairs = [], []
    for _, res, cv, req in items:
        kind, prems = judge.premises(res, cv)
        kinds.append(kind)
        pairs.append([(p, hypothesis(req)) for p in prems])
    return list(zip(kinds, judge.item_probs(pairs)))


def verdicts(judge, items, kp, tau):
    judge.tau_pass = judge.tau_fail = tau
    return [judge.verdict(res, p, k) for (_, res, _, _), (k, p) in zip(items, kp)]


def metrics(items, findings):
    rows = [(r, f) for (r, *_), f in zip(items, findings) if f.judge_verdict != "NOT_APPLICABLE"]
    err = [r["decision"] != r["gold_decision"] for r, _ in rows]

    def prf(flag):
        tp = sum(f and e for f, e in zip(flag, err))
        fp = sum(f and not e for f, e in zip(flag, err))
        fn = sum(e and not f for f, e in zip(flag, err))
        p = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        return {"precision": p, "recall": rc, "f1": 2 * p * rc / (p + rc) if p + rc else 0.0,
                "false_positive_flag_rate": fp / max(1, err.count(False)), "flags": tp + fp}
    strict = [f.judge_verdict == "FAIL" for _, f in rows]
    broad = [f.judge_verdict in ("FAIL", "UNCERTAIN") for _, f in rows]
    # wrongness score for AUROC / correctness confidence for ECE
    conf = []
    for (r, f) in rows:
        e, n, c = (f.nli_probs[k] for k in ("entailment", "neutral", "contradiction"))
        sup = e if r["decision"] == "MET" else (c if f.premise_kind == "quotes" else 1 - e)
        conf.append(sup)
    pos = [1 - c for c, e in zip(conf, err) if e]
    neg = [1 - c for c, e in zip(conf, err) if not e]
    auroc = (sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg))) if pos and neg else None
    bins = [[] for _ in range(10)]
    for c, e in zip(conf, err):
        bins[min(9, int(c * 10))].append((c, not e))
    ece = sum(len(b) * abs(sum(c for c, _ in b) / len(b) - sum(ok for _, ok in b) / len(b)) for b in bins if b) / len(conf) if conf else None
    tags = sorted({t for r, _ in rows for t in r["tags"]})
    per_tag = {}
    for t in tags:
        idx = [i for i, (r, _) in enumerate(rows) if t in r["tags"] and err[i]]
        if idx:
            per_tag[t] = {"errors": len(idx), "detected_strict": sum(strict[i] for i in idx) / len(idx)}
    return {"n_applicable": len(rows), "n_errors": sum(err), "strict": prf(strict), "broad": prf(broad),
            "auroc_error_detection": auroc, "ece_correctness": ece, "per_tag_error_detection": per_tag,
            "verdicts": {v: sum(f.judge_verdict == v for f in findings) for v in ("PASS", "FAIL", "UNCERTAIN", "NOT_APPLICABLE")}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--judge-dir", required=True)
    ap.add_argument("--name", default="judge")
    ap.add_argument("--tau", type=float)
    ap.add_argument("--calibrate-only", action="store_true")
    a = ap.parse_args()
    judge = NLIJudge(a.judge_dir, name=a.name)
    cfg, items = load(a.run)
    kp = probs_for(judge, items)
    if a.calibrate_only:
        assert cfg["split"] == "train", "calibrate on train-dev only"
        grid = [round(0.3 + 0.05 * i, 2) for i in range(14)]
        scores = {t: metrics(items, verdicts(judge, items, kp, t))["strict"]["f1"] for t in grid}
        best = max(scores, key=scores.get)
        out = {"run": a.run, "judge": a.name, "grid_f1": scores, "tau": best}
        print(json.dumps(out))
        Path(ROOT / "judge").mkdir(exist_ok=True)
        (ROOT / "judge" / f"calibration_{a.name}.json").write_text(json.dumps(out, indent=2) + "\n")
        return
    tau = a.tau if a.tau is not None else json.loads((ROOT / "judge" / f"calibration_{a.name}.json").read_text())["tau"]
    findings = verdicts(judge, items, kp, tau)
    m = {"run": a.run, "judge": a.name, "judge_dir": a.judge_dir, "tau": tau, **metrics(items, findings)}
    out = ROOT / "judge" / f"{a.run}__{a.name}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "judged.jsonl").write_text("".join(json.dumps({"case_id": r["case_id"], "req_id": r["req_id"],
                                                          "decision": r["decision"], "gold": r["gold_decision"],
                                                          "tags": r["tags"], **f.to_dict()}) + "\n"
                                              for (r, *_), f in zip(items, findings)))
    (out / "metrics.json").write_text(json.dumps(m, indent=2) + "\n")
    print(json.dumps({k: m[k] for k in ("run", "judge", "tau", "n_applicable", "n_errors", "strict", "auroc_error_detection",
                                        "ece_correctness")}))


if __name__ == "__main__":
    main()
