"""Counterfactual Bias Auditor evaluation on val requirements (extra Matcher calls, separate from normal inference).

For each selected (case, requirement): run the Matcher on variant A and B of each protected attribute
(matcher.bias_audit.ATTRIBUTES), compare validated decisions. Reports flip rate overall and per attribute.
Controls (no model): `biased_mock` must be flagged (known-bias detection), `lexical` must not (false-positive check).
Resumable: findings.jsonl keyed by (case_id, req_id).

  python -m benchmark.bias_eval --backend openai --model Qwen/Qwen3-4B-Instruct-2507 --base-url http://127.0.0.1:8080/v1 --n 30 --run-id bias-qwen3-4b-q4
  python -m benchmark.bias_eval --backend biased_mock --n 30 --run-id bias-biased-mock
"""
import argparse
import json
import random

from matcher.agent import Matcher
from matcher.backends import LexicalBaseline, MockBackend
from matcher.bias_audit import ATTRIBUTES, counterfactual
from matcher.knowledge import RagKnowledge
from matcher.schemas import CV, Requirement

from .compare import ROOT
from .run import DATA, read_jsonl


def biased_mock():
    """Known-bias regression fixture: answers like the keyword baseline but rejects the 'Tunisian' / 1966 variants."""
    lex = LexicalBaseline()

    def fn(t):
        if "Nationality: Tunisian" in t.cv.text or "Year of birth: 1966" in t.cv.text:
            return json.dumps({"decision": "MISSING", "basis": "not_documented", "evidence": [], "explanation": "biased fixture"})
        return lex.generate(t)
    return MockBackend(fn, label="biased_mock (known-bias fixture, not a model)")


def select(n, seed=0):
    items = [(c, r) for c in read_jsonl(DATA / "val.jsonl") for r in c["job"]["requirements"]]
    random.Random(seed).shuffle(items)
    return items[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", required=True, choices=["openai", "lexical", "biased_mock"])
    ap.add_argument("--model")
    ap.add_argument("--base-url")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--run-id", required=True)
    a = ap.parse_args()
    if a.backend == "openai":
        from matcher.backends_api import OpenAICompatBackend

        backend = OpenAICompatBackend(base_url=a.base_url, model=a.model, timeout=300)
    else:
        backend = LexicalBaseline() if a.backend == "lexical" else biased_mock()
    matcher = Matcher(backend, RagKnowledge())
    out = ROOT / "bias" / a.run_id
    out.mkdir(parents=True, exist_ok=True)
    path = out / "findings.jsonl"
    done = {(r["case_id"], r["req_id"]) for r in read_jsonl(path)} if path.exists() else set()
    with path.open("a") as f:
        for c, r in select(a.n):
            if (c["case_id"], r["req_id"]) in done:
                continue
            def match(cv, req):
                res = matcher.match_requirement(cv, req)[0]
                err = (getattr(backend, "last_call", None) or {}).get("error")
                if err:  # transport failure: abort, never count it as a decision (and never as a flip)
                    raise SystemExit(f"backend call failed at {c['case_id']}/{r['req_id']}: {err}; nothing recorded")
                return res
            fd = counterfactual(match, CV(**c["cv"]), Requirement(**r))
            f.write(json.dumps({"case_id": c["case_id"], "req_id": r["req_id"], "tags": c["gold"][r["req_id"]]["tags"],
                                **fd.to_dict()}) + "\n")
            f.flush()
    recs = read_jsonl(path)
    per = {attr: sum(x["details"][attr]["flip"] for x in recs) / len(recs) for attr in ATTRIBUTES}
    m = {"run_id": a.run_id, "backend": backend.info(), "n_requirements": len(recs), "calls": len(recs) * 2 * len(ATTRIBUTES),
         "flagged_rate": sum(x["audit_status"] == "FLAGGED" for x in recs) / len(recs), "flip_rate_per_attribute": per,
         "note": "A flip is a fairness signal for human review, not proof of discrimination."}
    (out / "metrics.json").write_text(json.dumps(m, indent=2) + "\n")
    print(json.dumps({k: m[k] for k in ("run_id", "n_requirements", "flagged_rate", "flip_rate_per_attribute")}))


if __name__ == "__main__":
    main()
