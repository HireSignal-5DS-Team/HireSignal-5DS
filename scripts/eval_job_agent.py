"""Evaluate the Job Agent on the real job offers against the gold cards.

    python scripts/eval_job_agent.py --base-url http://127.0.0.1:11434/v1 --mode inline
    python scripts/eval_job_agent.py --prompts job-v1 job-v2 --repeat 2 --name v1-vs-v2

Runs every prompt version on every offer in eval/job_agent/offers/, compares with
eval/job_agent/gold/, and writes eval/job_agent/results/<name>/:
  summary.md     table to paste into prompts/PROMPT_LIBRARY.md
  summary.json   all numbers
  <prompt>/<job_id>.json and .raw.txt   each card and the model's raw answer
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.job import BackendError, JobAgentError, NuExtractClient, PROMPT_VERSION, VERSIONS, run_job_agent  # noqa: E402
from agents.job.scoring import Score, score_card  # noqa: E402

OFFERS = ROOT / "eval/job_agent/offers"
GOLD = ROOT / "eval/job_agent/gold"


def signature(card: dict | None) -> tuple:
    """What must stay identical between two runs for them to count as 'stable'."""
    if card is None:
        return ()
    return tuple(sorted((r["text"], r["kind"], r["category"], str(r["min_years"])) for r in card["requirements"]))


def run_prompt(prompt: str, backend, job_ids: list[str], out_dir: Path, repeat: int) -> dict:
    total, per_offer, latencies, stable = Score(), {}, [], 0
    invented = repaired = review = errors = 0
    out_dir.mkdir(parents=True, exist_ok=True)

    for job_id in job_ids:
        post = (OFFERS / f"{job_id}.txt").read_text(encoding="utf-8")
        gold = json.loads((GOLD / f"{job_id}.json").read_text(encoding="utf-8"))
        runs = []
        for k in range(repeat):
            start = time.perf_counter()
            try:
                card = run_job_agent(post, job_id, backend, prompt_version=prompt).model_dump()
                error = None
            except JobAgentError as exc:
                card, error = None, str(exc)
            latencies.append(time.perf_counter() - start)
            runs.append(card)
            if k == 0:
                (out_dir / f"{job_id}.raw.txt").write_text(getattr(backend, "last_raw", ""), encoding="utf-8")
                (out_dir / f"{job_id}.json").write_text(
                    json.dumps(card if card else {"error": error}, indent=2, ensure_ascii=False), encoding="utf-8")

        card = runs[0]
        if repeat > 1 and len({signature(c) for c in runs}) == 1:
            stable += 1
        if card is None:
            errors += 1
            s = Score(fn=len(gold["requirements"]), unmatched_gold=[g["req_id"] for g in gold["requirements"]])
        else:
            s = score_card(card["requirements"], gold["requirements"])
            invented += sum("dropped as invented" in w for w in card["warnings"])
            repaired += sum("repaired" in w or "->" in w for w in card["warnings"])
            review += card["needs_human_review"]
        total.add(s)
        per_offer[job_id] = {
            "gold": len(gold["requirements"]), "predicted": 0 if card is None else len(card["requirements"]),
            "tp": s.tp, "fp": s.fp, "fn": s.fn, "precision": round(s.precision, 3), "recall": round(s.recall, 3),
            "f1": round(s.f1, 3), "missed": s.unmatched_gold, "extra": s.unmatched_pred,
            "error": None if card is not None else "no valid requirement",
        }
        print(f"  {prompt} {job_id}: gold {per_offer[job_id]['gold']:>2}  pred {per_offer[job_id]['predicted']:>2}"
              f"  P {s.precision:.2f}  R {s.recall:.2f}  F1 {s.f1:.2f}")

    return {
        "precision": round(total.precision, 3), "recall": round(total.recall, 3), "f1": round(total.f1, 3),
        "tp": total.tp, "fp": total.fp, "fn": total.fn,
        "kind_accuracy": round(total.accuracy("kind_ok"), 3),
        "category_accuracy": round(total.accuracy("category_ok"), 3),
        "years_accuracy": round(total.accuracy("years_ok"), 3),
        "invented_dropped": invented, "repairs": repaired, "needs_human_review": review, "failed_offers": errors,
        "mean_latency_s": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "stable_offers": f"{stable}/{len(job_ids)}" if repeat > 1 else "not measured (repeat 1)",
        "per_offer": per_offer,
    }


def to_markdown(results: dict, meta: dict) -> str:
    prompts = list(results)
    rows = [
        ("Precision (kept requirements that are correct)", "precision"),
        ("Recall (gold requirements found)", "recall"),
        ("F1", "f1"),
        ("Correct / extra / missed", None),
        ("kind accuracy (on matched)", "kind_accuracy"),
        ("category accuracy (on matched)", "category_accuracy"),
        ("min_years accuracy (on matched)", "years_accuracy"),
        ("Invented quotes dropped by guardrails", "invented_dropped"),
        ("Cards flagged for human review", "needs_human_review"),
        ("Offers with no valid card", "failed_offers"),
        ("Mean latency per offer (s)", "mean_latency_s"),
        ("Stable across repeats", "stable_offers"),
    ]
    lines = [f"**Job Agent evaluation** ({meta['date']}, {meta['offers']} real offers, "
             f"{meta['gold_requirements']} gold requirements, model `{meta['model']}`, mode `{meta['mode']}`, "
             f"repeat {meta['repeat']})", "",
             "| Measure | " + " | ".join(f"`{p}`" for p in prompts) + " |",
             "|---|" + "---|" * len(prompts)]
    for label, key in rows:
        if key is None:
            cells = [f"{r['tp']} / {r['fp']} / {r['fn']}" for r in results.values()]
        else:
            cells = [str(r[key]) for r in results.values()]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines += ["", "Per offer (F1):", "", "| Offer | gold | " + " | ".join(f"`{p}`" for p in prompts) + " |",
              "|---|---|" + "---|" * len(prompts)]
    for job_id in next(iter(results.values()))["per_offer"]:
        gold_n = next(iter(results.values()))["per_offer"][job_id]["gold"]
        lines.append(f"| {job_id} | {gold_n} | " + " | ".join(
            f"{r['per_offer'][job_id]['f1']}" for r in results.values()) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Evaluate the Job Agent against the gold cards")
    parser.add_argument("--prompts", nargs="+", default=sorted(VERSIONS), choices=sorted(VERSIONS))
    parser.add_argument("--repeat", type=int, default=1, help="runs per offer, to measure stability")
    parser.add_argument("--offers", nargs="*", help="only these job ids (default: all with a gold card)")
    parser.add_argument("--base-url")
    parser.add_argument("--mode", choices=["kwargs", "inline"])
    parser.add_argument("--name", help="results folder name (default: date-time)")
    args = parser.parse_args()

    job_ids = args.offers or sorted(p.stem for p in GOLD.glob("*.json"))
    backend = NuExtractClient(base_url=args.base_url, mode=args.mode)
    name = args.name or datetime.now().strftime("%Y%m%d-%H%M")
    out = ROOT / "eval/job_agent/results" / name
    gold_n = sum(len(json.loads((GOLD / f"{j}.json").read_text(encoding="utf-8"))["requirements"]) for j in job_ids)
    print(f"Evaluating {args.prompts} on {len(job_ids)} offers ({gold_n} gold requirements) -> {out}")

    results = {}
    try:
        for prompt in args.prompts:
            results[prompt] = run_prompt(prompt, backend, job_ids, out / prompt, args.repeat)
    except BackendError as exc:
        sys.exit(f"MODEL ERROR: {exc}")

    meta = {"date": datetime.now().strftime("%Y-%m-%d"), "offers": len(job_ids), "gold_requirements": gold_n,
            "model": backend.model, "mode": backend.mode, "repeat": args.repeat, "active_prompt": PROMPT_VERSION}
    (out / "summary.json").write_text(json.dumps({"meta": meta, "results": results}, indent=2), encoding="utf-8")
    md = to_markdown(results, meta)
    (out / "summary.md").write_text(md, encoding="utf-8")
    print("\n" + md + f"\nSaved {out / 'summary.md'}")


if __name__ == "__main__":
    main()
