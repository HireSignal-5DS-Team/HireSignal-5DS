r"""Anonymiser evaluation (rules only, no model).

1. Synthetic CVs with gold identity (tests/fixtures/profile/, from V2 eval/profile_agent/): identity leaks (target 0),
   other people readable, CV facts kept.
2. The 40 real Djinni CVs (data/processed/cvs/, Reader -> anonymiser exactly as /reader + /profile do): how many
   [NAME] replacements, and which detected "names" were replaced.
   The detected names go only to private/anonymiser_eval/<name>/names.json (git-ignored); the results folder keeps
   counts plus the detected values that are listed in --not-names (a hand check: words that are not person names).

Usage: .venv\Scripts\python scripts\eval_anonymiser.py --out eval\results\<date>_anonymiser_fix\before
"""
# Adapted from team V2: scripts/eval_privacy.py (readable, the leak / others / kept counts) (feature/agent-integration @ a5a03ff)
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.profile import anonymise_cv  # noqa: E402
from services.profile.detect import fold  # noqa: E402
from services.reader import read_cv  # noqa: E402

SYN = ROOT / "tests/fixtures/profile"


def _word(text, value):
    return re.search(r"(?<!\w)" + re.escape(fold(value)) + r"(?!\w)", fold(text)) is not None


def readable(anon, kind, value):
    """Can someone still read this identity piece in the anonymised text? (V2 eval_privacy.readable)"""
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


def synthetic():
    rows, t = [], {"leaks": 0, "hide": 0, "others": 0, "others_total": 0, "kept": 0, "keep": 0}
    for gold_file in sorted((SYN / "gold").glob("*.json")):
        gold = json.loads(gold_file.read_text(encoding="utf-8"))
        anon = anonymise_cv((SYN / "cvs" / f"{gold['cv']}.txt").read_text(encoding="utf-8"), cv_id="cv-00000000").text
        leaks = [f"{h['kind']}:{h['value']}" for h in gold["must_hide"] if readable(anon, h["kind"], h["value"])]
        others = [f"{h['kind']}:{h['value']}" for h in gold["other_people"] if readable(anon, h["kind"], h["value"])]
        lost = [k for k in gold["must_keep"] if k not in anon]
        t["leaks"] += len(leaks); t["hide"] += len(gold["must_hide"])  # noqa: E702
        t["others"] += len(others); t["others_total"] += len(gold["other_people"])  # noqa: E702
        t["kept"] += len(gold["must_keep"]) - len(lost); t["keep"] += len(gold["must_keep"])  # noqa: E702
        rows.append({"cv": gold["cv"], "leaks": leaks, "other_people_readable": others, "facts_lost": lost})
    return {"cvs": len(rows), "identity_pieces": t["hide"], "leaks": t["leaks"], "other_people_pieces": t["others_total"],
            "other_people_readable": t["others"], "facts": t["keep"], "facts_kept": t["kept"], "per_cv": rows}


def real(not_names):
    per, names = [], {}
    for cv in sorted((ROOT / "data/processed/cvs").glob("*.txt")):
        r = read_cv(cv)
        res = anonymise_cv(r.text, cv_id="cv-00000000", sections=r.sections)
        n = res.text.count("[NAME]")
        names[cv.stem] = res.identity.name
        per.append({"cv": cv.stem, "name_replacements": n, "name_found": res.identity.name is not None,
                    "not_a_name": res.identity.name in not_names})
    return per, names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--not-names", default="", help="file with one detected value per line that is not a person name")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    not_names = set(Path(a.not_names).read_text(encoding="utf-8").splitlines()) if a.not_names else set()
    syn = synthetic()
    per, names = real(not_names)
    priv = ROOT / "private" / "anonymiser_eval" / out.name
    priv.mkdir(parents=True, exist_ok=True)
    (priv / "names.json").write_text(json.dumps(names, indent=1, ensure_ascii=False), encoding="utf-8")
    found = [p for p in per if p["name_found"]]
    summary = {"label": "rules only, no model (CPU)", "synthetic": syn,
               "real_40": {"cvs": len(per), "cvs_with_a_detected_name": len(found),
                           "name_replacements_total": sum(p["name_replacements"] for p in per),
                           "detected_names_checked_not_a_name": sorted({names[p["cv"]] for p in found if p["not_a_name"]}),
                           "detected_names_not_in_not_a_name_list": sum(not p["not_a_name"] for p in found),
                           "per_cv": per}}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"synthetic: leaks {syn['leaks']}/{syn['identity_pieces']}, others readable {syn['other_people_readable']}/"
          f"{syn['other_people_pieces']}, facts kept {syn['facts_kept']}/{syn['facts']}")
    r = summary["real_40"]
    print(f"real 40: CVs with a detected name {r['cvs_with_a_detected_name']}, [NAME] replacements "
          f"{r['name_replacements_total']}, detected values outside the not-a-name list {r['detected_names_not_in_not_a_name_list']}")
    print(f"detected names (private): {priv / 'names.json'}")


if __name__ == "__main__":
    main()
