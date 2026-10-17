"""Step 4 evaluation: read the 10 synthetic CVs (after anonymisation) with Qwen, score against parse_gold.

    python scripts/eval_profile_parse.py                         (Qwen from HS_LLM_BASE_URL / HS_LLM_MODEL)
    python scripts/eval_profile_parse.py --llm-url http://127.0.0.1:11434/v1 --name q1-ollama

Saves eval/profile_agent/parse_results/<name>/ : per CV the ParsedCV, the model's raw answers, the scores,
and summary.json (micro-averaged over the 10 CVs).
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.job.backend import BackendError, QwenChatClient  # noqa: E402
from agents.profile import PROMPT_VERSION, anonymise_cv, parse_cv  # noqa: E402
from agents.profile.prompts import VERSIONS  # noqa: E402
from agents.profile.scoring import _prf, score_parsed  # noqa: E402

EVAL = ROOT / "eval" / "profile_agent"


class RecordingBackend:
    """Keeps every raw answer, not only the last one."""

    def __init__(self, inner):
        self.inner, self.calls = inner, []

    def extract(self, text, template, examples):
        raw = self.inner.extract(text, template, examples)
        self.calls.append({"input": text, "answer": raw, **(getattr(self.inner, "last_call", {}) or {})})
        return raw

    @property
    def last_call(self):
        return getattr(self.inner, "last_call", {})

    def info(self):
        return self.inner.info()


def run(backend, prompt: str, name: str) -> dict:
    out_dir = EVAL / "parse_results" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    totals = {k: {"tp": 0, "fp": 0, "fn": 0} for k in ("skills", "experience", "education")}
    fields = {"experience": {"title": [], "start": [], "end": []},
              "education": {"degree": [], "field": [], "institution": [], "end": []}}
    rows = []
    print(f"{'CV':<28}{'skills F1':>10}{'exp F1':>8}{'edu F1':>8}{'calls':>7}{'sec':>7}")
    for gold_file in sorted((EVAL / "parse_gold").glob("*.json")):
        gold = json.loads(gold_file.read_text(encoding="utf-8"))
        text = (EVAL / "cvs" / f"{gold['cv']}.txt").read_text(encoding="utf-8")
        anon = anonymise_cv(text, cv_id=gold["cv"])
        rec = RecordingBackend(backend)
        t0 = time.time()
        parsed = parse_cv(anon.text, anon.cv_id, rec, prompt).model_dump()
        secs = time.time() - t0
        scores = score_parsed(parsed, gold)
        for k in totals:
            for m in ("tp", "fp", "fn"):
                totals[k][m] += scores[k][m]
        for k, fs in fields.items():
            for f in fs:
                acc = scores[k].get(f"{f}_accuracy")
                matched = scores[k]["tp"]
                if acc is not None:
                    fs[f].append((acc, matched))
        (out_dir / f"{gold['cv']}.parsed.json").write_text(json.dumps(parsed, indent=1, ensure_ascii=False), encoding="utf-8")
        (out_dir / f"{gold['cv']}.raw.json").write_text(json.dumps(rec.calls, indent=1, ensure_ascii=False), encoding="utf-8")
        rows.append({"cv": gold["cv"], "seconds": round(secs, 1), "calls": len(rec.calls), **scores})
        print(f"{gold['cv']:<28}{scores['skills']['f1']:>10.3f}{scores['experience']['f1']:>8.3f}"
              f"{scores['education']['f1']:>8.3f}{len(rec.calls):>7}{secs:>7.1f}")
        if scores["skills"]["missed"] or scores["skills"]["extra"]:
            print(f"    skills missed {scores['skills']['missed']}  extra {scores['skills']['extra']}")
        for k in ("experience", "education"):
            for err in scores[k]["field_errors"]:
                print(f"    {k}: got {err['got']}")
    summary = {"prompt": prompt, "backend": backend.info(), "cvs": len(rows),
               **{k: _prf(**v) for k, v in totals.items()},
               "field_accuracy": {k: {f: round(sum(a * n for a, n in v) / max(1, sum(n for _, n in v)), 3)
                                      for f, v in fs.items() if v} for k, fs in fields.items()},
               "seconds_per_cv": round(sum(r["seconds"] for r in rows) / max(1, len(rows)), 1),
               "per_cv": rows}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nskills F1 {summary['skills']['f1']}   experience F1 {summary['experience']['f1']}   "
          f"education F1 {summary['education']['f1']}   {summary['seconds_per_cv']} s per CV")
    print(f"field accuracy {summary['field_accuracy']}")
    print(f"Saved {out_dir}")
    return summary


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Profile Agent step 4 evaluation")
    parser.add_argument("--prompt", choices=sorted(VERSIONS), default=PROMPT_VERSION)
    parser.add_argument("--llm-url", help="Qwen server (default HS_LLM_BASE_URL)")
    parser.add_argument("--name", help="results folder (default: the prompt version)")
    args = parser.parse_args()
    try:
        backend = QwenChatClient(base_url=args.llm_url, max_tokens=3072)
    except ValueError as exc:
        sys.exit(f"CONFIG ERROR: {exc}")
    print(f"Profile Agent step 4 ({args.prompt}) -> {backend.info()}")
    try:
        run(backend, args.prompt, args.name or args.prompt)
    except BackendError as exc:
        sys.exit(f"MODEL ERROR: {exc}")


if __name__ == "__main__":
    main()
