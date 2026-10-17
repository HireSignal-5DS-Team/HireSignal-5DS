"""Evaluate the Job Agent on the real job offers against the gold cards.

    python scripts/eval_job_agent.py --base-url http://127.0.0.1:11434/v1 --mode inline
    python scripts/eval_job_agent.py --prompts job-v1 job-v2 --repeat 2 --name v1-vs-v2
    python scripts/eval_job_agent.py --rescore v2-vs-v3     (re-score a saved run, no model needed)

Runs every prompt version on every offer in eval/job_agent/offers/, compares with
eval/job_agent/gold/, and writes eval/job_agent/results/<name>/:
  summary.md     table to paste into prompts/PROMPT_LIBRARY.md
  summary.json   all numbers
  <prompt>/<job_id>.json and .raw.txt   each card and ALL the model's raw answers (one per call)

Three scores (agents/job/scoring.py):
  sentences  were the requirement sentences of the offer found?          (main score)
  skills     on the sentences found, were the skill names right?
  strict     full requirement: right sentence AND a shared skill name     (first score used)
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
from agents.job.scoring import Score, TermScore, score_card, score_sentences, score_skill_terms  # noqa: E402

OFFERS = ROOT / "eval/job_agent/offers"
GOLD = ROOT / "eval/job_agent/gold"


def signature(card: dict | None) -> tuple:
    """What must stay identical between two runs for them to count as 'stable'."""
    if card is None:
        return ()
    return tuple(sorted((r["text"], r["kind"], r["category"], str(r["min_years"])) for r in card["requirements"]))


class RecordingBackend:
    """Wraps the model client and keeps every raw answer (the chunked strategy makes many calls)."""

    def __init__(self, backend):
        self.backend, self.log = backend, []

    @property
    def last_call(self):
        return getattr(self.backend, "last_call", {})

    def extract(self, text, template, examples):
        raw = self.backend.extract(text, template, examples)
        self.log.append((text, raw))
        return raw

    def dump(self) -> str:
        return "\n\n".join(f"### call {i} - input starts: {' '.join(t.split())[:80]!r}\n{raw}"
                             for i, (t, raw) in enumerate(self.log, start=1))


def score_offer(card: dict | None, gold: dict) -> dict:
    reqs = [] if card is None else card["requirements"]
    strict = score_card(reqs, gold["requirements"])
    sent, pairs = score_sentences(reqs, gold["requirements"])
    terms = score_skill_terms(reqs, gold["requirements"], pairs)
    return {"strict": strict, "sentences": sent, "terms": terms}


def summarise(per_offer_scores: list[dict], extra: dict) -> dict:
    strict, sent, terms = Score(), Score(), TermScore()
    for s in per_offer_scores:
        strict.add(s["strict"])
        sent.add(s["sentences"])
        terms.add(s["terms"])
    r3 = lambda x: round(x, 3)  # noqa: E731
    return {
        "sentences": {"precision": r3(sent.precision), "recall": r3(sent.recall), "f1": r3(sent.f1),
                      "tp": sent.tp, "fp": sent.fp, "fn": sent.fn,
                      "kind_accuracy": r3(sent.accuracy("kind_ok")),
                      "category_accuracy": r3(sent.accuracy("category_ok")),
                      "years_accuracy": r3(sent.accuracy("years_ok"))},
        "skills": {"precision": r3(terms.precision), "recall": r3(terms.recall), "f1": r3(terms.f1),
                   "tp": terms.tp, "fp": terms.fp, "fn": terms.fn},
        "strict": {"precision": r3(strict.precision), "recall": r3(strict.recall), "f1": r3(strict.f1),
                   "tp": strict.tp, "fp": strict.fp, "fn": strict.fn},
        **extra,
    }


def run_prompt(prompt: str, backend, job_ids: list[str], out_dir: Path, repeat: int) -> dict:
    scores, per_offer, latencies, stable = [], {}, [], 0
    invented = repaired = review = errors = 0
    out_dir.mkdir(parents=True, exist_ok=True)

    for job_id in job_ids:
        post = (OFFERS / f"{job_id}.txt").read_text(encoding="utf-8")
        gold = json.loads((GOLD / f"{job_id}.json").read_text(encoding="utf-8"))
        runs = []
        for k in range(repeat):
            recorder = RecordingBackend(backend)
            start = time.perf_counter()
            try:
                card = run_job_agent(post, job_id, recorder, prompt_version=prompt).model_dump()
                error = None
            except JobAgentError as exc:
                card, error = None, str(exc)
            latencies.append(time.perf_counter() - start)
            runs.append(card)
            if k == 0:
                (out_dir / f"{job_id}.raw.txt").write_text(recorder.dump(), encoding="utf-8")
                (out_dir / f"{job_id}.json").write_text(
                    json.dumps(card if card else {"error": error}, indent=2, ensure_ascii=False), encoding="utf-8")

        card = runs[0]
        if repeat > 1 and len({signature(c) for c in runs}) == 1:
            stable += 1
        if card is None:
            errors += 1
        else:
            invented += sum("dropped as invented" in w for w in card["warnings"])
            repaired += sum("repaired" in w or "->" in w for w in card["warnings"])
            review += card["needs_human_review"]
        s = score_offer(card, gold)
        scores.append(s)
        per_offer[job_id] = {"gold_sentences": s["sentences"].tp + s["sentences"].fn,
                             "sentences_f1": round(s["sentences"].f1, 3), "skills_f1": round(s["terms"].f1, 3),
                             "strict_f1": round(s["strict"].f1, 3), "missed_sentences": s["sentences"].unmatched_gold,
                             "extra_sentences": s["sentences"].unmatched_pred}
        print(f"  {prompt} {job_id}: sentences F1 {s['sentences'].f1:.2f}  skills F1 {s['terms'].f1:.2f}"
              f"  strict F1 {s['strict'].f1:.2f}")

    return summarise(scores, {
        "invented_dropped": invented, "repairs": repaired, "needs_human_review": review, "failed_offers": errors,
        "mean_latency_s": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "stable_offers": f"{stable}/{len(job_ids)}" if repeat > 1 else "not measured (repeat 1)",
        "per_offer": per_offer,
    })


def rescore(name: str, job_ids: list[str]) -> tuple[dict, dict]:
    """Re-score the cards saved by an earlier run (no model call). Stability/latency come from its summary."""
    folder = ROOT / "eval/job_agent/results" / name
    old = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    results = {}
    for prompt_dir in sorted(p for p in folder.iterdir() if p.is_dir()):
        scores, per_offer = [], {}
        for job_id in job_ids:
            gold = json.loads((GOLD / f"{job_id}.json").read_text(encoding="utf-8"))
            saved = json.loads((prompt_dir / f"{job_id}.json").read_text(encoding="utf-8"))
            s = score_offer(saved if "requirements" in saved else None, gold)
            scores.append(s)
            per_offer[job_id] = {"gold_sentences": s["sentences"].tp + s["sentences"].fn,
                                 "sentences_f1": round(s["sentences"].f1, 3), "skills_f1": round(s["terms"].f1, 3),
                                 "strict_f1": round(s["strict"].f1, 3)}
        prev = old["results"].get(prompt_dir.name, {})
        results[prompt_dir.name] = summarise(scores, {
            k: prev.get(k) for k in ("invented_dropped", "needs_human_review", "failed_offers",
                                     "mean_latency_s", "stable_offers")} | {"per_offer": per_offer})
    meta = dict(old["meta"], rescored=datetime.now().strftime("%Y-%m-%d"))
    return results, meta


def to_markdown(results: dict, meta: dict) -> str:
    prompts = list(results)
    head = "| Measure | " + " | ".join(f"`{p}`" for p in prompts) + " |"
    sep = "|---|" + "---|" * len(prompts)

    def row(label, get):
        return f"| {label} | " + " | ".join(str(get(r)) for r in results.values()) + " |"

    lines = [f"**Job Agent evaluation** ({meta['date']}{', re-scored ' + meta['rescored'] if meta.get('rescored') else ''}, "
             f"{meta['offers']} real offers, {meta['gold_requirements']} gold requirements, model `{meta['model']}`, "
             f"mode `{meta['mode']}`, repeat {meta['repeat']})", "",
             "**1. Requirement sentences found** (main score: did the agent find each requirement of the offer?)", "",
             head, sep,
             row("Precision", lambda r: r["sentences"]["precision"]),
             row("Recall", lambda r: r["sentences"]["recall"]),
             row("**F1**", lambda r: f"**{r['sentences']['f1']}**"),
             row("Found / extra / missed", lambda r: f"{r['sentences']['tp']} / {r['sentences']['fp']} / {r['sentences']['fn']}"),
             row("kind accuracy (on found)", lambda r: r["sentences"]["kind_accuracy"]),
             row("category accuracy (on found)", lambda r: r["sentences"]["category_accuracy"]),
             row("min_years accuracy (on found)", lambda r: r["sentences"]["years_accuracy"]),
             "", "**2. Skill names** (on the sentences found: are the skill_terms right?)", "", head, sep,
             row("Precision", lambda r: r["skills"]["precision"]),
             row("Recall", lambda r: r["skills"]["recall"]),
             row("**F1**", lambda r: f"**{r['skills']['f1']}**"),
             row("Right / wrong / missing", lambda r: f"{r['skills']['tp']} / {r['skills']['fp']} / {r['skills']['fn']}"),
             "", "**3. Strict** (full requirement: right sentence AND a shared skill name)", "", head, sep,
             row("F1", lambda r: r["strict"]["f1"]),
             row("Correct / extra / missed", lambda r: f"{r['strict']['tp']} / {r['strict']['fp']} / {r['strict']['fn']}"),
             "", "**Other**", "", head, sep,
             row("Invented quotes dropped by guardrails", lambda r: r.get("invented_dropped")),
             row("Offers with no valid card", lambda r: r.get("failed_offers")),
             row("Mean latency per offer (s)", lambda r: r.get("mean_latency_s")),
             row("Stable across repeats", lambda r: r.get("stable_offers")),
             "", "Per offer (sentences F1 / skills F1):", "",
             "| Offer | sentences | " + " | ".join(f"`{p}`" for p in prompts) + " |",
             "|---|---|" + "---|" * len(prompts)]
    first = next(iter(results.values()))["per_offer"]
    for job_id in first:
        lines.append(f"| {job_id} | {first[job_id]['gold_sentences']} | " + " | ".join(
            f"{r['per_offer'][job_id]['sentences_f1']} / {r['per_offer'][job_id]['skills_f1']}"
            for r in results.values()) + " |")
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
    parser.add_argument("--rescore", metavar="NAME", help="re-score a saved run (writes rescore.md, keeps summary.md)")
    args = parser.parse_args()

    job_ids = args.offers or sorted(p.stem for p in GOLD.glob("*.json"))
    if args.rescore:
        results, meta = rescore(args.rescore, job_ids)
        folder = ROOT / "eval/job_agent/results" / args.rescore
        (folder / "rescore.json").write_text(json.dumps({"meta": meta, "results": results}, indent=2), encoding="utf-8")
        md = to_markdown(results, meta)
        (folder / "rescore.md").write_text(md, encoding="utf-8")
        print(md + f"\nSaved {folder / 'rescore.md'}")
        return

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
