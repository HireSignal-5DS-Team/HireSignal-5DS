"""Export the RAG knowledge-base data to CSV and verify it against the pinned upstream sources.

Reads only; never writes to the RAG data folder.

  RAG_DIR  : checkout of `rag/` from branch claude/gracious-fermi-ncuem4 (the files the RAG indexes)
  UP_DIR   : folder holding the pinned upstream files, hash-checked here:
             2026_09.parquet (HF abigailhaddad/usajobs-scraping @ 9f20234) and
             mirror/data-sets/csv/esco-v1.1.2/*.csv (tabiya-tech/taxonomy-model-application @ eb3e5f4)

Usage: python export_csv.py RAG_DIR UP_DIR
Output: esco_ict_skills_1621.csv, real_job_offers_20.csv next to this script, and an audit dump on stdout.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

OUT = Path(__file__).parent
RAG, UP = Path(sys.argv[1]), Path(sys.argv[2])
ESCO_DIR = UP / "mirror/data-sets/csv/esco-v1.1.2"
PINNED = {  # copied from rag/build_esco.py and rag/build_jobs.py
    ESCO_DIR / "skills.csv": "9717a4521c94cc0eeefe519b2fccddac0a406a729d519bf3357e8ed60723fee2",
    ESCO_DIR / "occupations.csv": "99ebee8b5d1ee376d00b0633b4e941167e37dcf0247ec7e8d4533a7a44dd7cfc",
    ESCO_DIR / "occupation_to_skill_relations.csv": "28e4565583797edee7c3f20b743548cfefc9483683d549724ca69b2c9a9eb6d5",
    UP / "2026_09.parquet": "fb6e2e30d0d7b274e6f8f84dec9bd722025049325c165aaebdaf9725a49c6a97",
}
for p, h in PINNED.items():
    assert hashlib.sha256(p.read_bytes()).hexdigest() == h, f"hash mismatch: {p}"
    print(f"sha256 ok  {p.name}")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def audit(name, df, key):
    print(f"\n== {name}: rows={len(df)} cols={len(df.columns)} unique {key}={df[key].nunique()} "
          f"duplicate rows={df.astype(str).duplicated().sum()} duplicate {key}={df[key].duplicated().sum()}")
    for c in df.columns:
        s = df[c]
        empty = int((s.isna() | (s.astype(str).str.strip() == "")).sum())
        print(f"  {c}: empty={empty} max_len={int(s.fillna("").astype(str).str.len().max())}")


# ---------- ESCO ----------
jl = RAG / "data/esco/esco_ict_skills.jsonl"
rag_esco = pd.DataFrame([json.loads(l) for l in jl.read_text(encoding="utf-8").splitlines() if l.strip()])
sk = pd.read_csv(ESCO_DIR / "skills.csv", dtype=str, keep_default_na=False)
occ = pd.read_csv(ESCO_DIR / "occupations.csv", dtype=str, keep_default_na=False)
rel = pd.read_csv(ESCO_DIR / "occupation_to_skill_relations.csv", dtype=str, keep_default_na=False)
assert not sk.ORIGINURI.duplicated().any()
esco = rag_esco.merge(sk, left_on="doc_id", right_on="ORIGINURI", how="left", validate="one_to_one")
assert esco.ORIGINURI.notna().all(), "JSONL concept missing from upstream skills.csv"
# selection rule of build_esco.py must give exactly the JSONL set
linked = set(rel[rel.OCCUPATIONID.isin(occ[occ.CODE.str.match(r"^(25|35|212|1330)")].ID)].SKILLID)
assert set(sk[sk.ID.isin(linked) | (sk.REUSELEVEL == "transversal")].ORIGINURI) == set(rag_esco.doc_id)
# every JSONL text must be rebuilt exactly from the upstream row (label + alt labels + description)
for r in esco.itertuples():
    alts = [a for a in r.ALTLABELS.split("\n") if a and a != r.PREFERREDLABEL]
    text = (r.PREFERREDLABEL + (". Also known as: " + "; ".join(alts) if alts else "") + ". " + r.DESCRIPTION).strip()
    assert (text, r.PREFERREDLABEL, r.SKILLTYPE, r.REUSELEVEL) == (r.text, r.title, r.skill_type, r.reuse_level), r.doc_id
assert (esco.url == esco.doc_id).all()
print(f"\nESCO: all {len(esco)} JSONL rows match upstream skills.csv exactly; selection rule reproduces the set")
esco = esco.assign(
    source_dataset="ESCO classification v1.1.x (en), European Commission",
    source_mirror="https://github.com/tabiya-tech/taxonomy-model-application",
    source_commit="eb3e5f445f6c0271641851dd2d27621d812c4662",
    source_file="data-sets/csv/esco-v1.1.2/skills.csv",
    source_sha256=PINNED[ESCO_DIR / "skills.csv"],
    rag_file="rag/data/esco/esco_ict_skills.jsonl",
    rag_file_sha256=sha(jl),
    license="CC BY 4.0 - attribution: ESCO, European Commission",
)
audit("ESCO", esco, "doc_id")
esco.to_csv(OUT / "esco_ict_skills_1621.csv", index=False, encoding="utf-8-sig")  # BOM so Excel reads UTF-8

# ---------- Jobs ----------
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")  # same redaction as rag/build_jobs.py
PHONE = re.compile(r"\(?\b\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b")
SECTIONS = [("Summary", "jobSummary"), ("Duties", "majorDuties"), ("Conditions of employment", "conditionsOfEmployment"),
            ("Qualifications", "qualificationSummary"), ("Education", "education"),
            ("Additional information", "additionalInformation")]
src = pd.read_parquet(UP / "2026_09.parquet")
rows, redactions = [], 0
for md in sorted((RAG / "data/jobs").glob("usajobs-*.md")):
    raw = md.read_text(encoding="utf-8")
    _, head, body = raw.split("---\n", 2)
    meta = dict(l.split(": ", 1) for l in head.strip().splitlines())
    cn = meta["job_id"].removeprefix("usajobs-")
    up = src[src.usajobsControlNumber == cn]
    assert len(up) == 1, cn
    u = up.iloc[0]
    rebuilt = "\n\n".join(f"{h}\n{u[c].strip()}" for h, c in SECTIONS if isinstance(u[c], str) and u[c].strip())
    rebuilt = PHONE.sub("[contact removed]", EMAIL.sub("[contact removed]", rebuilt))
    assert rebuilt + "\n" == body, f"{md.name} body differs from upstream"
    assert (meta["title"], meta["organisation"], meta["open_date"]) == (u.positionTitle, u.hiringAgencyName, u.positionOpenDate)
    # upstream columns verbatim, except e-mails/phones redacted with the project's own rule (rag/data/jobs/README.md)
    orig = {}
    for c, v in u.items():
        if isinstance(v, str):
            n = len(EMAIL.findall(v)) + len(PHONE.findall(EMAIL.sub("", v)))
            redactions += n
            v = PHONE.sub("[contact removed]", EMAIL.sub("[contact removed]", v))
        orig[f"src_{c}"] = v
    rows.append({**meta, "rag_file": f"rag/data/jobs/{md.name}", "rag_file_sha256": sha(md),
                 "rag_text": body.rstrip("\n"), "rag_text_words": len(body.split()), **orig})
jobs = pd.DataFrame(rows)
print(f"\nJobs: all {len(jobs)} RAG bodies rebuild byte-for-byte from upstream; "
      f"{redactions} e-mail/phone strings redacted in src_* columns")
audit("Jobs", jobs, "job_id")
jobs.to_csv(OUT / "real_job_offers_20.csv", index=False, encoding="utf-8-sig")
