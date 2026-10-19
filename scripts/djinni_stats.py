r"""Profile the Djinni English parquet files (data/raw/djinni/): rows, columns, top Primary Keyword, CV length,
rough regex counts of personal data left in CV text. Writes data/stats/djinni_stats.json (counts only, no CV text).

Usage: .venv\Scripts\python scripts\djinni_stats.py
"""
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/djinni"
# Rough PII patterns (shortcut: regex over-/under-counts, e.g. version numbers as phones; a real check is the T-anonymiser)
PII = {"email": r"[\w.+-]+@[\w-]+\.[\w.]+",
       "url_profile": r"(?i)linkedin\.com|github\.com|t\.me/|telegram|skype",
       "name_phrase": r"(?i)\bmy name is\b|\bname\s*:"}

PHONE = re.compile(r"(?<![\w.])\+?\(?\d[\d \-()]{8,}\d(?![\w.])")
YEAR_RANGE = re.compile(r"^\(?(19|20)\d\d([-./]\d\d)?\D+(19|20)\d\d")


def has_phone(s):
    """>= 10 digits in one number-like run, and not a year range such as '2019 - 2021'."""
    return any(sum(ch.isdigit() for ch in m) >= 10 and not YEAR_RANGE.match(m) for m in PHONE.findall(s))


def describe(df, keyword_col, text_col):
    lens = df[text_col].fillna("").str.len()
    return {"rows": len(df), "columns": list(df.columns),
            "top_primary_keyword": df[keyword_col].value_counts().head(25).to_dict(),
            f"{text_col}_chars": {k: round(float(v), 1) for k, v in lens.describe(percentiles=[.1, .5, .9]).items()}}


def main():
    cvs = pd.read_parquet(next((RAW / "candidate-profiles-english").rglob("*.parquet")))
    jobs = pd.read_parquet(next((RAW / "job-descriptions-english").rglob("*.parquet")))
    out = {"cvs": describe(cvs, "Primary Keyword", "CV"), "jobs": describe(jobs, "Primary Keyword", "Long Description")}
    text = cvs["CV"].fillna("")
    out["cvs"]["cv_lang"] = cvs["CV_lang"].value_counts().to_dict()
    out["cvs"]["experience_years"] = cvs["Experience Years"].value_counts().sort_index().to_dict()
    out["cvs"]["pii_regex_rows"] = {k: int(text.str.contains(p, regex=True).sum()) for k, p in PII.items()}
    phone = text.map(has_phone)
    out["cvs"]["pii_regex_rows"]["phone"] = int(phone.sum())
    # self-check of the phone rule
    assert has_phone("call +380 67 123 45 67") and has_phone("(050) 123-45-67 x")
    assert not has_phone("2019 - 2021 (2 years)") and not has_phone("2018-09 - 2021-03")
    other = text.str.contains("|".join(f"(?:{p})" for p in PII.values()).replace("(?i)", ""), regex=True, flags=re.I)
    out["cvs"]["pii_regex_rows_any"] = int((other | phone).sum())
    out["jobs"]["lang"] = jobs["Long Description_lang"].value_counts().to_dict()
    (ROOT / "data/stats").mkdir(exist_ok=True)
    (ROOT / "data/stats/djinni_stats.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
