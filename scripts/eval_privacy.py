"""Privacy evaluation of the Profile Agent on the synthetic CVs (eval/profile_agent).

    python scripts/eval_privacy.py                               (rules only)
    python scripts/eval_privacy.py --ner gliner resume-ner --name with-ner

For each CV, against the hand-written gold:
- leaks       : candidate identity still readable in the anonymised text  (target: 0)
- others      : other people's names / contacts still readable (references) (rules alone miss names)
- kept        : CV facts (companies, dates, skills) still intact            (target: 100%)
This checker is independent from the agent's own leak check, on purpose.
Saves eval/profile_agent/results/<name>/ : one anonymised text per CV + summary.json.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.profile import anonymise_cv, make_detectors  # noqa: E402
from agents.profile.detect import fold  # noqa: E402

EVAL = ROOT / "eval" / "profile_agent"


def _word(text: str, value: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(fold(value)) + r"(?!\w)", fold(text)) is not None


def readable(anon: str, kind: str, value: str) -> bool:
    """Can someone still read this identity piece in the anonymised text?"""
    if kind == "PHONE":
        key = re.sub(r"\D", "", value)[-8:]
        runs = [re.sub(r"\D", "", m.group(0)) for m in re.finditer(r"\+?\d[\d \t().\-/]*\d", anon)]
        return any(key in r for r in runs)
    if kind == "NAME":
        words = [w for w in re.split(r"[\s\-]+", value) if len(w) >= 3]
        letters = re.sub(r"[^a-z]", "", fold(anon))
        glued = len(words) >= 2 and (fold(words[0] + words[-1]) in letters)
        return glued or any(_word(anon, w) for w in words)
    return _word(anon, value) if len(value) <= 12 else fold(value) in fold(anon)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Profile Agent privacy evaluation")
    parser.add_argument("--ner", nargs="*", default=[], help="resume-ner and/or gliner (CPU)")
    parser.add_argument("--name", help="results folder name (default: rules or the NER names)")
    args = parser.parse_args()

    detectors = make_detectors(args.ner)
    name = args.name or ("rules" if not args.ner else "rules+" + "+".join(args.ner))
    out_dir = EVAL / "results" / name
    out_dir.mkdir(parents=True, exist_ok=True)

    rows, totals = [], {"leaks": 0, "hide": 0, "others": 0, "others_total": 0, "kept": 0, "keep": 0}
    print(f"{'CV':<28}{'leaks':>7}{'others':>8}{'kept':>8}{'review':>8}{'sec':>6}")
    for gold_file in sorted((EVAL / "gold").glob("*.json")):
        gold = json.loads(gold_file.read_text(encoding="utf-8"))
        text = (EVAL / "cvs" / f"{gold['cv']}.txt").read_text(encoding="utf-8")
        t0 = time.time()
        result = anonymise_cv(text, cv_id=gold["cv"], detectors=detectors)
        secs = time.time() - t0
        anon = result.text

        leaks = [f"{h['kind']}:{h['value']}" for h in gold["must_hide"] if readable(anon, h["kind"], h["value"])]
        others = [f"{h['kind']}:{h['value']}" for h in gold["other_people"] if readable(anon, h["kind"], h["value"])]
        lost = [k for k in gold["must_keep"] if k not in anon]
        kept = len(gold["must_keep"]) - len(lost)

        totals["leaks"] += len(leaks)
        totals["hide"] += len(gold["must_hide"])
        totals["others"] += len(others)
        totals["others_total"] += len(gold["other_people"])
        totals["kept"] += kept
        totals["keep"] += len(gold["must_keep"])
        rows.append({"cv": gold["cv"], "leaks": leaks, "other_people_readable": others, "facts_lost": lost,
                     "needs_human_review": result.report.needs_human_review, "seconds": round(secs, 2),
                     "report": result.report.model_dump()})
        (out_dir / f"{gold['cv']}.anon.txt").write_text(anon, encoding="utf-8")
        print(f"{gold['cv']:<28}{len(leaks):>7}{len(others):>8}{kept:>5}/{len(gold['must_keep']):<2}"
              f"{str(result.report.needs_human_review):>8}{secs:>6.1f}")
        for item in leaks:
            print(f"    LEAK   {item}")
        for item in others:
            print(f"    other  {item}")
        for item in lost:
            print(f"    lost   {item!r}")

    summary = {
        "detectors": ["rules"] + [d.name for d in detectors if not d.error],
        "detector_errors": [d.error for d in detectors if d.error],
        "cvs": len(rows),
        "identity_pieces": totals["hide"], "leaks": totals["leaks"],
        "leak_rate": round(totals["leaks"] / max(1, totals["hide"]), 4),
        "other_people_pieces": totals["others_total"], "other_people_readable": totals["others"],
        "facts": totals["keep"], "facts_kept": totals["kept"],
        "facts_kept_rate": round(totals["kept"] / max(1, totals["keep"]), 4),
        "per_cv": rows,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nIdentity leaks: {totals['leaks']}/{totals['hide']}   "
          f"other people readable: {totals['others']}/{totals['others_total']}   "
          f"facts kept: {totals['kept']}/{totals['keep']}")
    for err in summary["detector_errors"]:
        print(f"! {err}")
    print(f"Saved {out_dir}")


if __name__ == "__main__":
    main()
