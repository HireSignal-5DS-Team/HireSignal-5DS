r"""T15 Part A: Job Agent prompt versions on real job offers vs gold cards (real-GPU, plain Qwen3-4B on llama-server).

Set: 10 USAJOBS offers with V2's gold cards (eval/job_agent/) + our J1-J4 with the recruiter-confirmed cards.
Split fixed before any run (by sorted id): dev = first 5 USAJOBS + J1, J2; test = last 5 USAJOBS + J3, J4.

Matching rule (services/job/scoring.py, from V2): a predicted requirement SENTENCE matches a gold one when the quotes
overlap (one contains the other, or difflib similarity >= 0.60 after normalisation); one-to-one, best pairs first.
Measures per version:
  sentences P / R / F1 (main), must/nice accuracy on matched, skills F1 and strict F1 (V2's other two scores);
  invented   = proposed quotes not found in the offer (dropped by the guardrails);
  verbatim   = share of the model's raw proposals whose quote is an exact substring of the offer;
  soft_must  = kept MUST items that are soft traits (SOFT regex below, no skill term) - gold never has a soft must;
  splits     = gold sentences matched by >= 2 different predicted quotes; merges = predicted quotes overlapping >= 2
               gold sentences;
  latency per offer.
Usage: .venv\Scripts\python scripts\eval_job_prompts.py --versions job-v1 job-v2 --split dev --out eval\results\<d>_job_prompts
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.job import JobAgentError, run_job_agent  # noqa: E402
from services.job.qwen_retry import ResilientQwenChatClient  # noqa: E402
from services.job.scoring import _evidence_overlap, score_card, score_sentences, score_skill_terms  # noqa: E402
from services.job.validate import parse_model_output  # noqa: E402

USA = sorted(p.stem for p in (ROOT / "eval/job_agent/offers").glob("usajobs-*.txt"))
SPLITS = {"dev": USA[:5] + ["J1", "J2"], "test": USA[5:] + ["J3", "J4"]}
# soft ATTITUDES (not named competencies such as "Teamwork" or "Oral Communication", which V2's gold keeps as must)
SOFT = re.compile(r"(?i)\b(willing\w*|wiliness|eager\w*|motivated|passionate|passion for|curious|curiosity|proactive|"
                  r"self-starter|team player|friendly|open-minded)\b")


def load(job: str) -> tuple[str, dict]:
    if job.startswith("usajobs"):
        return ((ROOT / f"eval/job_agent/offers/{job}.txt").read_text(encoding="utf-8"),
                json.loads((ROOT / f"eval/job_agent/gold/{job}.json").read_text(encoding="utf-8")))
    return ((ROOT / f"data/processed/jobs/{job}.txt").read_text(encoding="utf-8"),
            json.loads((ROOT / f"data/processed/jobs/{job}_requirements.json").read_text(encoding="utf-8")))


class Recorder:
    def __init__(self, backend):
        self.backend, self.log = backend, []

    @property
    def last_call(self):
        return getattr(self.backend, "last_call", {})

    def extract(self, text, template, examples):
        raw = self.backend.extract(text, template, examples)
        self.log.append({"input": text, "raw": raw, "finish": (self.last_call or {}).get("finish_reason")})
        return raw


def raw_items(log: list[dict]) -> list[dict]:
    out = []
    for call in log:
        try:
            data = parse_model_output(call["raw"])
        except (ValueError, TypeError):
            continue
        out += [r for r in data.get("requirements", []) if isinstance(r, dict)] if isinstance(data, dict) else []
    return out


def score_job(card: dict | None, gold: dict, post: str, log: list[dict]) -> dict:
    reqs = (card or {}).get("requirements", [])
    sent, pairs = score_sentences(reqs, gold["requirements"])
    terms = score_skill_terms(reqs, gold["requirements"], pairs)
    strict = score_card(reqs, gold["requirements"])
    raws = [r for r in raw_items(log) if isinstance(r.get("evidence"), str) and "evidence" in r]
    pred_q = list(dict.fromkeys(r["evidence"] for r in reqs))
    gold_q = list(dict.fromkeys(r["evidence"] for r in gold["requirements"]))
    return {
        "tp": sent.tp, "fp": sent.fp, "fn": sent.fn, "kind_ok": sent.kind_ok,
        "terms_tp": terms.tp, "terms_fp": terms.fp, "terms_fn": terms.fn,
        "strict_tp": strict.tp, "strict_fp": strict.fp, "strict_fn": strict.fn,
        "raw_proposals": len(raws), "raw_verbatim": sum(r["evidence"].strip() in post for r in raws),
        "invented": sum("dropped as invented" in w for w in (card or {}).get("warnings", [])),
        "soft_must": [r["evidence"] for r in reqs if r["kind"] == "must" and not r["skill_terms"]
                      and SOFT.search(r["evidence"])],
        "splits": [g for g in gold_q if sum(_evidence_overlap(p, g) for p in pred_q) >= 2],
        "merges": [p for p in pred_q if sum(_evidence_overlap(p, g) for g in gold_q) >= 2],
        "cut_calls": sum(c["finish"] == "length" for c in log),
        "missed": sent.unmatched_gold, "extra": sent.unmatched_pred,
    }


def summarise(rows: list[dict]) -> dict:
    s = lambda k: sum(r[k] for r in rows)  # noqa: E731
    p = s("tp") / (s("tp") + s("fp")) if s("tp") + s("fp") else 0
    r = s("tp") / (s("tp") + s("fn")) if s("tp") + s("fn") else 0
    tp, fp, fn = s("terms_tp"), s("terms_fp"), s("terms_fn")
    st, sf, sn = s("strict_tp"), s("strict_fp"), s("strict_fn")
    f = lambda a, b, c: round(2 * a / (2 * a + b + c), 3) if a else 0.0  # noqa: E731
    return {"offers": len(rows), "gold_sentences": s("tp") + s("fn"), "found": s("tp"), "extra": s("fp"),
            "missed": s("fn"), "precision": round(p, 3), "recall": round(r, 3),
            "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0,
            "kind_accuracy": round(s("kind_ok") / s("tp"), 3) if s("tp") else None,
            "skills_f1": f(tp, fp, fn), "strict_f1": f(st, sf, sn),
            "invented_dropped": s("invented"),
            "verbatim_rate": round(s("raw_verbatim") / s("raw_proposals"), 3) if s("raw_proposals") else None,
            "soft_must": sum(len(r["soft_must"]) for r in rows),
            "splits": sum(len(r["splits"]) for r in rows), "merges": sum(len(r["merges"]) for r in rows),
            "cut_calls": s("cut_calls"), "failed": sum(r["failed"] for r in rows),
            "latency_s_mean": round(sum(r["latency_s"] for r in rows) / len(rows), 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--versions", nargs="+", default=["job-v1"])
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-tokens", type=int, default=768)  # = JOB_MAX_TOKENS in /job
    ap.add_argument("--rescore", action="store_true", help="recompute the scores from the saved runs, no model")
    a = ap.parse_args()
    out = Path(a.out)
    summary = {}
    for v in a.versions:
        rows = []
        (out / v / a.split).mkdir(parents=True, exist_ok=True)
        for job in SPLITS[a.split]:
            post, gold = load(job)
            if a.rescore:
                saved = json.loads((out / v / a.split / f"{job}.json").read_text(encoding="utf-8"))
                old = saved["score"]
                row = {"job": job, "failed": old["failed"], "latency_s": old["latency_s"],
                       **score_job(saved["card"], gold, post, saved["calls"])}
                rows.append(row)
                saved["score"] = row
                (out / v / a.split / f"{job}.json").write_text(json.dumps(saved, indent=1, ensure_ascii=False),
                                                              encoding="utf-8")
                continue
            rec = Recorder(ResilientQwenChatClient(max_tokens=a.max_tokens, lora_scale=0.0))
            t = time.perf_counter()
            try:
                card, failed = run_job_agent(post, job, rec, prompt_version=v).model_dump(), 0
            except JobAgentError as exc:
                card, failed = {"error": str(exc), "requirements": [], "warnings": []}, 1
            row = {"job": job, "failed": failed, "latency_s": round(time.perf_counter() - t, 1),
                   **score_job(card, gold, post, rec.log)}
            rows.append(row)
            (out / v / a.split / f"{job}.json").write_text(json.dumps({"card": card, "score": row, "calls": rec.log},
                                                                      indent=1, ensure_ascii=False), encoding="utf-8")
            f1 = 2 * row["tp"] / (2 * row["tp"] + row["fp"] + row["fn"]) if row["tp"] else 0
            print(v, a.split, job, f"F1 {f1:.2f} tp {row['tp']} fp {row['fp']} fn {row['fn']} soft_must "
                  f"{len(row['soft_must'])} splits {len(row['splits'])} merges {len(row['merges'])} "
                  f"{row['latency_s']}s", flush=True)
        summary[v] = {"all": summarise(rows), "usajobs": summarise([r for r in rows if r["job"].startswith("usa")]),
                      "djinni": summarise([r for r in rows if not r["job"].startswith("usa")]),
                      "per_job": {r["job"]: {k: r[k] for k in ("tp", "fp", "fn", "soft_must", "splits", "merges",
                                                                   "latency_s")} for r in rows}}
        print(v, a.split, json.dumps(summary[v]["all"]), flush=True)
    path = out / f"summary_{a.split}.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    path.write_text(json.dumps({**old, **summary, "label": "real-GPU, plain Qwen3-4B (llama-server)",
                                "max_tokens": a.max_tokens, "split_jobs": SPLITS[a.split]}, indent=1),
                    encoding="utf-8")


if __name__ == "__main__":
    main()
