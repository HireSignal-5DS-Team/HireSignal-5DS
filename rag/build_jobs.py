"""Build the job-posting collection from real USAJOBS announcements.

Source: "USAJOBS announcement text" (Hugging Face dataset abigailhaddad/usajobs-scraping, CC0 1.0), a scrape of
usajobs.gov pages. The announcements are works of the U.S. federal government: public domain (17 U.S.C. 105).
Revision and file hash are pinned, so the collection is reproducible.

Each posting is written as the page's own sections, in page order, under the page's own headings. Section text
is copied verbatim from the dataset (the scraper collapsed whitespace, so original line breaks are lost).
Only requirement-relevant sections are kept; Benefits, How you will be evaluated, Required documents and
How to apply are left out (application logistics, not job requirements).

Usage: python rag/build_jobs.py
"""
import hashlib
import re
import subprocess
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
OUT = HERE / "data/jobs"
CACHE = HERE / "data/jobs/_src"  # gitignored
DATASET = "abigailhaddad/usajobs-scraping"
REVISION = "9f202342df2d8db692c0ad973905a808b835db89"
FILE = "data/2026_09.parquet"
SHA256 = "fb6e2e30d0d7b274e6f8f84dec9bd722025049325c165aaebdaf9725a49c6a97"

# One posting per agency, chosen for role diversity: data scientists, ML/AI engineers, AI software engineers,
# statisticians, IT specialists (AI / data science). Selection made from titles only, before any query was written.
CONTROL_NUMBERS = [
    "882803700", "882835500", "882960000", "883048600", "883161100", "883284100", "883337000", "883386100",
    "883511200", "883691200", "883699600", "883827900", "884225200", "884301900", "884501900", "884783000",
    "885581200", "885947600", "886071700", "886606600",
]
SECTIONS = [("Summary", "jobSummary"), ("Duties", "majorDuties"), ("Conditions of employment", "conditionsOfEmployment"),
            ("Qualifications", "qualificationSummary"), ("Education", "education"),
            ("Additional information", "additionalInformation")]
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"\(?\b\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b")


def fetch():
    path = CACHE / Path(FILE).name
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/{FILE}"
        subprocess.run(["curl", "-sSfL", "-o", str(path), url], check=True)
    if hashlib.sha256(path.read_bytes()).hexdigest() != SHA256:
        raise SystemExit(f"hash mismatch for {path}")
    return pd.read_parquet(path)


def build():
    df = fetch().set_index("usajobsControlNumber")
    for cn in CONTROL_NUMBERS:
        r = df.loc[cn]
        body = "\n\n".join(f"{head}\n{r[col].strip()}" for head, col in SECTIONS if isinstance(r[col], str) and r[col].strip())
        body = PHONE.sub("[contact removed]", EMAIL.sub("[contact removed]", body))
        header = "\n".join([
            "---", f"job_id: usajobs-{cn}", f"title: {r.positionTitle}", f"organisation: {r.hiringAgencyName}",
            f"source_url: https://www.usajobs.gov/job/{cn}",
            f"retrieved: 2026-10-13 via huggingface.co/datasets/{DATASET} @ {REVISION[:7]} ({FILE})",
            "rights: public domain (work of the U.S. federal government, 17 U.S.C. 105); dataset CC0 1.0",
            f"open_date: {r.positionOpenDate}", "---", ""])
        (OUT / f"usajobs-{cn}.md").write_text(header + body + "\n", encoding="utf-8")
    print(f"wrote {len(CONTROL_NUMBERS)} postings to {OUT}")


if __name__ == "__main__":
    build()
