"""Counterfactual Bias Auditor evaluation on val requirements (extra Matcher calls, separate from normal inference).

For each selected (case, requirement): run the Matcher on variant A and B of each attribute
(matcher.bias_audit.ALL_ATTRIBUTES), compare validated decisions. Reports flip rate overall and per attribute with
Wilson 95 % intervals, flips caused by an invalid model output, call latency p50/p95 and (with --server-pid) the
model server's peak RSS.
Attribute sets: core (name, gender, nationality, age: the original audit, default), extended (+ disability, religion,
family, address, career-gap reason), all (= extended + placebo_hobby). The placebo changes a NON-protected hobby
line: its flip rate is the instability floor; protected flips are read against it. new+placebo = only the 5 new
protected attributes + placebo, to complement an existing core run on the same requirements without repeating it.
Controls (no model): `biased_mock` must be flagged (known-bias detection), `lexical` must not (false-positive check).
--compare-to <run dir>: paired comparison on the shared (requirement, attribute) cells, exact McNemar test on flips.
Resumable: findings.jsonl keyed by (case_id, req_id). Same seed and n give the same requirements as the base run.

  # base Matcher (measured 2026, BM25 RAG): 1/30 flagged
  python -m benchmark.bias_eval --backend openai --model Qwen/Qwen3-4B-Instruct-2507 --base-url http://127.0.0.1:8080/v1 --n 30 --run-id bias-qwen3-4b-q4
  # LoRA Matcher (window 1): see bias/run_window1.sh
  python -m benchmark.bias_eval --backend openai --model Qwen/Qwen3-4B-Instruct-2507+lora --base-url http://127.0.0.1:8081/v1 \
      --adapter-id HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora --adapter-revision <sha> --attributes all --n 30 \
      --run-id bias-qwen3-4b-q4+hslora --compare-to benchmark/results/bias/bias-qwen3-4b-q4
  python -m benchmark.bias_eval --backend biased_mock --rag none --n 30 --run-id bias-biased-mock
"""
import argparse
import json
import random
from pathlib import Path

from matcher.agent import Matcher
from matcher.backends import LexicalBaseline, MockBackend
from matcher.bias_audit import ALL_ATTRIBUTES, ATTRIBUTES, EXTENDED_ATTRIBUTES, PLACEBO_ATTRIBUTES, counterfactual
from matcher.schemas import CV, Requirement

from .compare import ROOT
from .run import DATA, read_jsonl

ATTRIBUTE_SETS = {"core": tuple(ATTRIBUTES), "extended": (*ATTRIBUTES, *EXTENDED_ATTRIBUTES), "all": tuple(ALL_ATTRIBUTES),
                  # the 5 new protected attributes + placebo only: complements a core run on the same requirements
                  "new+placebo": (*EXTENDED_ATTRIBUTES, *PLACEBO_ATTRIBUTES)}


def biased_mock():
    """Known-bias regression fixture: answers like the keyword baseline but rejects the 'Tunisian' / 1966 /
    Saint-Denis / wheelchair variants."""
    lex = LexicalBaseline()
    triggers = ("Nationality: Tunisian", "Year of birth: 1966", "93200 Saint-Denis", "Accessibility needs: wheelchair")

    def fn(t):
        if any(x in t.cv.text for x in triggers):
            return json.dumps({"decision": "MISSING", "basis": "not_documented", "evidence": [], "explanation": "biased fixture"})
        return lex.generate(t)
    return MockBackend(fn, label="biased_mock (known-bias fixture, not a model)")


def select(n, seed=0):
    items = [(c, r) for c in read_jsonl(DATA / "val.jsonl") for r in c["job"]["requirements"]]
    random.Random(seed).shuffle(items)
    return items[:n]


def summarize(recs, attrs):
    from bias.stats import wilson as w

    n = len(recs)
    out = {}
    for attr in attrs:
        cells = [x["details"][attr] for x in recs if attr in x["details"]]
        k = sum(c["flip"] for c in cells)
        inv = sum(c["flip"] and bool(c.get("invalid")) for c in cells)
        out[attr] = {"flips": k, "n": len(cells), "rate": k / len(cells) if cells else None, "ci95": w(k, len(cells)),
                     "flips_with_invalid_output": inv}
    protected = [a for a in attrs if a not in PLACEBO_ATTRIBUTES]
    flagged = sum(any(x["details"][a]["flip"] for a in protected if a in x["details"]) for x in recs)
    return out, {"n_requirements": n, "flagged_requirements": flagged, "flagged_rate": flagged / n if n else None,
                 "flagged_ci95": w(flagged, n)}


def paired(recs, ref_dir):
    from bias.stats import exact_binom_two_sided

    ref = {(r["case_id"], r["req_id"]): r for r in read_jsonl(Path(ref_dir) / "findings.jsonl")}
    only_new = only_ref = both = 0
    cells = 0
    for x in recs:
        r = ref.get((x["case_id"], x["req_id"]))
        if not r:
            continue
        for attr, d in x["details"].items():
            if attr not in r["details"]:
                continue
            cells += 1
            a, b = d["flip"], r["details"][attr]["flip"]
            both += a and b
            only_new += a and not b
            only_ref += b and not a
    return {"reference": str(ref_dir), "shared_cells": cells, "flip_both": both, "flip_only_this_run": only_new,
            "flip_only_reference": only_ref, "mcnemar_exact_p": exact_binom_two_sided(only_new, only_new + only_ref)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", required=True, choices=["openai", "lexical", "biased_mock"])
    ap.add_argument("--model")
    ap.add_argument("--base-url")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--attributes", default="core", choices=sorted(ATTRIBUTE_SETS))
    ap.add_argument("--rag", default="bm25", choices=["bm25", "none"], help="bm25 = the setting of the base-Matcher run")
    ap.add_argument("--adapter-id", help="provenance only: the LoRA served behind --base-url")
    ap.add_argument("--adapter-revision")
    ap.add_argument("--server-pid", type=int, help="sample this process's RSS (the llama.cpp server)")
    ap.add_argument("--compare-to", help="reference run dir for a paired flip comparison")
    ap.add_argument("--run-id", required=True)
    a = ap.parse_args()
    if a.backend == "openai":
        from matcher.backends_api import OpenAICompatBackend

        backend = OpenAICompatBackend(base_url=a.base_url, model=a.model, timeout=300)
    else:
        backend = LexicalBaseline() if a.backend == "lexical" else biased_mock()
    if a.rag == "bm25":
        from matcher.knowledge import RagKnowledge

        knowledge = RagKnowledge()
    else:
        from matcher.knowledge import NoKnowledge

        knowledge = NoKnowledge()
    matcher = Matcher(backend, knowledge)
    attrs = ATTRIBUTE_SETS[a.attributes]
    out = ROOT / "bias" / a.run_id
    out.mkdir(parents=True, exist_ok=True)
    path = out / "findings.jsonl"
    done = {(r["case_id"], r["req_id"]) for r in read_jsonl(path)} if path.exists() else set()
    sampler = None
    if a.server_pid:
        from bias.review_eval import RssSampler

        sampler = RssSampler(a.server_pid)
        sampler.start()
    latencies = []
    with path.open("a") as f:
        for c, r in select(a.n, a.seed):
            if (c["case_id"], r["req_id"]) in done:
                continue
            invalid = {}

            def match(cv, req):
                res, info = matcher.match_requirement(cv, req)
                err = (getattr(backend, "last_call", None) or {}).get("error")
                if err:  # transport failure: abort, never count it as a decision (and never as a flip)
                    raise SystemExit(f"backend call failed at {c['case_id']}/{r['req_id']}: {err}; nothing recorded")
                latencies.append(info["latency_s"])
                invalid.setdefault(cv.text.split("\n", 1)[0], not info["parsed"])
                return res
            fd = counterfactual(match, CV(**c["cv"]), Requirement(**r), attributes=attrs)
            for attr in attrs:  # mark flips where either side was unparseable (validator UNCERTAIN, not a judgement)
                lines = [ALL_ATTRIBUTES[attr][2].format(v) for v in ALL_ATTRIBUTES[attr][:2]]
                fd.details[attr]["invalid"] = any(invalid.get(x) for x in lines)
            f.write(json.dumps({"case_id": c["case_id"], "req_id": r["req_id"], "tags": c["gold"][r["req_id"]]["tags"],
                                **fd.to_dict()}) + "\n")
            f.flush()
    if sampler:
        sampler.stop.set()
    recs = read_jsonl(path)
    from bias.stats import pct

    per_attr, overall = summarize(recs, attrs)
    info = backend.info()
    if a.adapter_id:
        info = {**info, "adapter_id": a.adapter_id, "adapter_revision": a.adapter_revision}
    m = {"run_id": a.run_id, "label": "LIVE" if info.get("is_model") else "MOCK (no model)", "backend": info,
         "knowledge": getattr(knowledge, "name", type(knowledge).__name__), "attributes": list(attrs), "seed": a.seed,
         **overall, "calls": len(recs) * 2 * len(attrs),
         # kept for compatibility with the first run's metrics.json
         "flip_rate_per_attribute": {k: v["rate"] for k, v in per_attr.items()}, "per_attribute": per_attr,
         "latency_p50_s": pct(latencies, 50), "latency_p95_s": pct(latencies, 95),
         "latency_note": "this invocation's new calls only" if done else "all calls",
         "server_peak_rss_mb": round(sampler.peak / 2**20, 1) if sampler else None,
         "note": "A flip is a fairness signal for human review, not proof of discrimination. flagged_rate counts "
                 "protected attributes only; placebo_hobby is the instability floor."}
    if a.compare_to:
        m["paired_vs_reference"] = paired(recs, a.compare_to)
    (out / "metrics.json").write_text(json.dumps(m, indent=2) + "\n")
    print(json.dumps({k: m[k] for k in ("run_id", "label", "n_requirements", "flagged_rate", "flip_rate_per_attribute")}))


if __name__ == "__main__":
    main()
