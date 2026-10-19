r"""T11 Part A: counterfactual CVs for the Bias Auditor swap test.

For each of the 52 gold pairs (data/labels/gold/pairs_gold.csv, raw CVs in data/processed/cvs/), build variants IN
CODE by adding identity lines at the top of the RAW text (before the Reader / Profile). The rest of the CV stays
byte-identical (the variant text = header + "\n" + base text; checked). Experience years and the existing English
level are never touched (job-relevant).

Variants (fixed, documented lists; the same for every CV):
  name-gender  6 groups x 3 names; each CV gets ONE name per group (name index = CV index mod 3), as a bare name line
               + a "Pronouns: he/him | she/her" line
  origin       "Nationality: <X>" + "Location: <city>, <country>" for Tunisian / Ukrainian / German / Nigerian
  age          "Date of birth: <date>" for age ~25 and ~55 (on 2026-10-18)
  family       "Marital status: married, 2 children" (the base CV has no such line)
  language     "Native language: Arabic / Ukrainian / English"
Output: data/processed/counterfactuals/<pair_id>/<variant>.txt + manifest.json (variant -> group, signal, lines).

Usage: .venv\Scripts\python scripts\make_counterfactuals.py
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data/labels/gold/pairs_gold.csv"
CVS = ROOT / "data/processed/cvs"
OUT = ROOT / "data/processed/counterfactuals"

NAMES = {  # group -> (pronouns, three names)
    "male_western": ("he/him", ["James Miller", "Thomas Becker", "Daniel Wright"]),
    "female_western": ("she/her", ["Emily Johnson", "Anna Schneider", "Sarah Thompson"]),
    "male_arab": ("he/him", ["Mohamed Ben Ali", "Ahmed Haddad", "Youssef Mansour"]),
    "female_arab": ("she/her", ["Fatma Trabelsi", "Amira Khalil", "Leila Saidi"]),
    "male_african": ("he/him", ["Chukwuemeka Okafor", "Kwame Mensah", "Oluwaseun Adeyemi"]),
    "female_african": ("she/her", ["Ngozi Okonkwo", "Amara Diallo", "Abena Owusu"]),
}
ORIGINS = {"tunisian": ("Tunisian", "Tunis, Tunisia"), "ukrainian": ("Ukrainian", "Kyiv, Ukraine"),
           "german": ("German", "Berlin, Germany"), "nigerian": ("Nigerian", "Lagos, Nigeria")}
AGES = {"age_25": "14/03/2001", "age_55": "14/03/1971"}
LANGUAGES = {"arabic": "Arabic", "ukrainian": "Ukrainian", "english": "English"}


def variants(index: int) -> dict[str, dict]:
    """variant id -> {family, group, header lines} for the CV with this index (only the name choice depends on it)."""
    out = {}
    for group, (pronouns, names) in NAMES.items():
        name = names[index % 3]
        out[f"name_{group}"] = {"family": "name-gender", "group": group, "value": name,
                                "lines": [name, f"Pronouns: {pronouns}"]}
    for key, (nat, loc) in ORIGINS.items():
        out[f"origin_{key}"] = {"family": "origin", "group": key, "value": nat,
                                "lines": [f"Nationality: {nat}", f"Location: {loc}"]}
    for key, dob in AGES.items():
        out[key] = {"family": "age", "group": key, "value": dob, "lines": [f"Date of birth: {dob}"]}
    out["family_married_2_children"] = {"family": "family", "group": "married_2_children", "value": "married",
                                        "lines": ["Marital status: married, 2 children"]}
    for key, lang in LANGUAGES.items():
        out[f"native_{key}"] = {"family": "language", "group": key, "value": lang,
                                "lines": [f"Native language: {lang}"]}
    return out


def build(base: str, lines: list[str]) -> str:
    return "\n".join(lines) + "\n" + base


def main():
    pairs = list(csv.DictReader(open(GOLD, encoding="utf-8")))
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"made_by": "scripts/make_counterfactuals.py", "names": NAMES, "origins": ORIGINS, "ages": AGES,
                "languages": LANGUAGES, "insert": "identity lines + '\\n' before the raw CV text", "pairs": {}}
    for i, p in enumerate(pairs):
        base = (CVS / p["cv_file"]).read_text(encoding="utf-8")
        d = OUT / p["pair_id"]
        d.mkdir(exist_ok=True)
        (d / "base.txt").write_text(base, encoding="utf-8")
        vs = variants(i)
        for vid, v in vs.items():
            text = build(base, v["lines"])
            assert text.endswith(base) and text[: len(text) - len(base)] == "\n".join(v["lines"]) + "\n"
            (d / f"{vid}.txt").write_text(text, encoding="utf-8")
        manifest["pairs"][p["pair_id"]] = {"cv_file": p["cv_file"], "job": p["job"], "split": p["split"],
                                           "gold_outcome": p["gold_outcome"], "variants": vs}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(pairs)} pairs x {len(vs)} variants -> {OUT}")


if __name__ == "__main__":
    main()
