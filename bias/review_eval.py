"""Evaluate Bias Auditor variants on the fairness test set (bias/data/*.jsonl).

For each item the Matcher answer is validated against its CV (matcher.validate), then every variant audits it.
Reports per variant: precision, recall, F1, false-positive rate on negative controls, recall per expected reason and
per attribute, Wilson 95 % intervals; for the reviewer also JSON-valid rate, errors, latency p50/p95 and (with
--server-pid) the peak RSS of the model server process. The rules-only variants are deterministic; the reviewer is
a live model call. Resumable: reviewer outputs are cached in reviews.jsonl keyed by item_id.

Backends:
  --backend none         rules only (no model)
  --backend mock         scripted keyword client, plumbing only; results are labelled MOCK, never a model result
  --backend openai       live reviewer, e.g. original Qwen3-4B-Instruct-2507 Q4_K_M on the fallback server :8080

  python -m bias.review_eval --backend none --splits dev,test,holdout --run-id review-rules
  python -m bias.review_eval --backend openai --base-url http://127.0.0.1:8080/v1 \
      --model Qwen/Qwen3-4B-Instruct-2507 --splits dev,test,holdout --run-id review-qwen3-4b-q4-p1 --server-pid <pid>
"""
import argparse
import json
import os
import platform
import re
import threading
import time
from pathlib import Path

from matcher.schemas import CV, ModelAnswer, Requirement
from matcher.validate import validate

from .auditor import BiasAuditor
from .reviewer import LLMReviewer
from .stats import pct, wilson

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).parent / "data"
RESULTS = ROOT / "benchmark" / "results" / "bias"
FEWSHOT_IDS = {"culture_fit-0", "collision_race-0", "evidence_birth_year-0"}  # dev items quoted in the prompt


class MockKeywordClient:
    """Scripted stand-in for the reviewer endpoint (NOT a model). Flags a handful of keywords; used for plumbing."""
    KW = re.compile(r"\b(woman|young|older|born|national|culture fit|wheelchair|mosque|married|mother)\b", re.I)

    def __init__(self):
        self.last_call = {}

    def info(self):
        return {"backend": "mock", "label": "mock_keyword_reviewer (scripted, not a model)", "is_model": False}

    def chat(self, messages, max_tokens=None):
        expl = messages[-1]["content"].split("Explanation:", 1)[-1]
        hit = self.KW.search(expl)
        self.last_call = {"latency_s": 0.0, "error": None, "prompt_tokens": None, "completion_tokens": None}
        return json.dumps({"flag": bool(hit), "category": "explanation_leak" if hit else "none",
                           "attributes": [hit.group(0).lower()] if hit else [], "rationale": "mock"})


class RssSampler(threading.Thread):
    """Peak RSS of a process (the model server), sampled every 0.5 s."""

    def __init__(self, pid):
        super().__init__(daemon=True)
        import psutil

        self.proc, self.peak, self.stop = psutil.Process(pid), 0, threading.Event()

    def run(self):
        while not self.stop.is_set():
            try:
                self.peak = max(self.peak, self.proc.memory_info().rss, hwm(self.proc.pid))
            except Exception:
                return
            time.sleep(0.5)


def hwm(pid):
    """Kernel peak-RSS high-water mark (VmHWM, bytes) of a process since it started; 0 if unavailable."""
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def load(splits):
    items = []
    for s in splits:
        p = DATA / f"{s}.jsonl"
        if not p.exists():
            raise SystemExit(f"missing {p}")
        items += [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    return items


def as_result(item):
    cv, req = CV(**item["cv"]), Requirement(**item["requirement"])
    return validate(ModelAnswer(**item["answer"]), cv, req, []), cv, req


def score(rows, key):
    pos = [r for r in rows if r["expected_flag"]]
    neg = [r for r in rows if not r["expected_flag"]]
    tp = sum(r[key] for r in pos)
    fp = sum(r[key] for r in neg)
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / len(pos) if pos else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else 0.0
    by = lambda field: {v: {"recall": sum(r[key] for r in pos if r[field] == v) / n, "n": n}  # noqa: E731
                        for v in sorted({r[field] for r in pos}) for n in [sum(r[field] == v for r in pos)]}
    return {"n": len(rows), "positives": len(pos), "negatives": len(neg), "tp": tp, "fp": fp,
            "precision": prec, "recall": rec, "recall_ci95": wilson(tp, len(pos)), "f1": f1,
            "false_positive_rate": fp / len(neg) if neg else None, "fpr_ci95": wilson(fp, len(neg)),
            "recall_by_reason": by("expected_reason"), "recall_by_attribute": by("attribute"),
            "fp_by_category": {c: sum(r[key] for r in neg if r["category"] == c) for c in sorted({r["category"] for r in neg})}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", required=True, choices=["none", "mock", "openai"])
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    ap.add_argument("--base-url", default="http://127.0.0.1:8080/v1")
    ap.add_argument("--prompt-id", default="reviewer_v1")
    ap.add_argument("--splits", default="dev,test")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--server-pid", type=int)
    a = ap.parse_args()
    items = load(a.splits.split(","))
    out = RESULTS / a.run_id
    out.mkdir(parents=True, exist_ok=True)

    reviewer = None
    if a.backend == "mock":
        reviewer = LLMReviewer(MockKeywordClient(), prompt_id=a.prompt_id)
    elif a.backend == "openai":
        from matcher.backends_api import OpenAICompatBackend

        reviewer = LLMReviewer(OpenAICompatBackend(base_url=a.base_url, model=a.model, timeout=300, max_tokens=160),
                               prompt_id=a.prompt_id)
    sampler = RssSampler(a.server_pid) if a.server_pid else None
    if sampler:
        sampler.start()

    cache_path = out / "reviews.jsonl"
    cache = {}
    if cache_path.exists():
        cache = {r["item_id"]: r["review"] for r in map(json.loads, cache_path.read_text().splitlines()) if r.get("review")}
    rules = {v: BiasAuditor(v) for v in ("rules_v1", "rules_v2")}
    rows = []
    with cache_path.open("a") as cf:
        for it in items:
            res, cv, req = as_result(it)
            row = {k: it[k] for k in ("item_id", "split", "family", "category", "expected_flag", "expected_reason", "attribute")}
            row["validated_decision"] = res.decision
            for v, aud in rules.items():
                row[v] = aud.check_result(res, cv.text, requirement_text=req.text).audit_status == "FLAGGED"
            if reviewer:
                rv = cache.get(it["item_id"])
                if rv is None:
                    rv = reviewer.review(res, req.text)
                    if rv["error"] and rv["error"] != "reviewer_output_invalid":
                        raise SystemExit(f"reviewer transport failure at {it['item_id']}: {rv['error']}; nothing recorded")
                    cf.write(json.dumps({"item_id": it["item_id"], "review": rv}, ensure_ascii=False) + "\n")
                    cf.flush()
                v = rv["verdict"]
                row["reviewer"] = bool(v and v["flag"])
                row["reviewer_error"] = rv["error"]
                row["reviewer_category"] = v["category"] if v else None
                row["reviewer_latency_s"] = rv["latency_s"]
                row["rules_v2+reviewer"] = row["rules_v2"] or row["reviewer"]
            rows.append(row)
    if sampler:
        sampler.stop.set()

    (out / "predictions.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    variants = ["rules_v1", "rules_v2"] + (["reviewer", "rules_v2+reviewer"] if reviewer else [])
    splits = a.splits.split(",")
    m = {"run_id": a.run_id, "label": {"none": "DETERMINISTIC (rules only, no model)", "mock": "MOCK (scripted reviewer, not a model)",
                                        "openai": "LIVE"}[a.backend],
         "reviewer": reviewer.info() if reviewer else None, "revision": os.environ.get("HS_LLM_REVISION"),
         "testset_manifest": json.loads((DATA / "MANIFEST.json").read_text()), "host": platform.node(),
         "note": f"fewshot items {sorted(FEWSHOT_IDS)} appear in the reviewer prompt; they are excluded from the dev scores",
         "scores": {}}
    for s in splits + ["all_reported"]:
        rs = [r for r in rows if (r["split"] == s if s != "all_reported" else r["split"] != "dev")]
        rs = [r for r in rs if r["item_id"] not in FEWSHOT_IDS or r["split"] != "dev"]
        if rs:
            m["scores"][s] = {v: score(rs, v) for v in variants}
    if reviewer:
        lat = [r["reviewer_latency_s"] for r in rows if r["reviewer_latency_s"] is not None]
        m["reviewer_ops"] = {"calls": len(rows), "json_valid_rate": sum(r["reviewer_error"] is None for r in rows) / len(rows),
                             "errors": sum(r["reviewer_error"] is not None for r in rows),
                             "latency_p50_s": pct(lat, 50), "latency_p95_s": pct(lat, 95),
                             "server_peak_rss_mb": round(sampler.peak / 2**20, 1) if sampler else None,
                             "server_rss_note": "peak RSS of the whole llama.cpp server process (VmHWM since server start), "
                                                "shared with the base Matcher fallback; not a reviewer-only cost"}
    (out / "metrics.json").write_text(json.dumps(m, indent=2) + "\n")
    brief = {s: {v: {k: (round(x[k], 3) if isinstance(x[k], float) else x[k]) for k in ("precision", "recall", "false_positive_rate")}
                 for v, x in sc.items()} for s, sc in m["scores"].items()}
    print(json.dumps({"run_id": a.run_id, "label": m["label"], "scores": brief, "ops": m.get("reviewer_ops")}, indent=1))


if __name__ == "__main__":
    main()
