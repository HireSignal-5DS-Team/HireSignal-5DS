"""Sample real Djinni CV x job pairs and write a human-labelling review file (xlsx + jsonl).

Data (MIT): lang-uk/recruitment-dataset-candidate-profiles-english, lang-uk/recruitment-dataset-job-descriptions-english.
Requirements are split from the job text by a heuristic and are only CANDIDATES: the reviewer keeps, edits or drops
each one and fills decision / basis / evidence. Nothing here is a label.

    python finetuning/sample_djinni.py --raw <dir with cvs.parquet, jobs.parquet> --out <review dir>
Output stays outside the repo (CV text must not be committed).
"""
import argparse
import json
import re
from pathlib import Path

import pandas as pd

SEED = 20261015
KEYWORDS = ["Python", "Java", "JavaScript", ".NET", "PHP", "Node.js", "DevOps", "QA Automation", "QA",
            "Data Science", "Android", "iOS", "C++", "Golang", "Ruby"]
PAIRS_PER_KEYWORD = 10
MAX_TEXT_REQS = 4

PII = [(re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
       (re.compile(r"https?://\S+|www\.\S+|\b[\w-]+\.(?:com|io|net|org|ua|dev)/\S*", re.I), "[URL]"),
       (re.compile(r"(?<!\w)@[A-Za-z_][\w]{3,}"), "[HANDLE]")]
HEADER = re.compile(r"(requirement|qualification|what we expect|you (have|are|should)|must have|skills|"
                    r"we are looking for|what you need|what we need|ideal candidate|nice to have|plus|bonus)", re.I)
STOP = re.compile(r"(we offer|benefits|responsibilit|what you will do|your tasks|duties|about (us|the company|the project)|"
                  r"why (us|join)|we provide|our offer|perks)", re.I)
NICE = re.compile(r"(nice to have|good to have|would be a plus|is a plus|bonus|preferred|advantage)", re.I)
YEARS = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", re.I)
ENGLISH = {"no_english": None, "basic": "Basic", "pre": "Pre-Intermediate", "intermediate": "Intermediate",
           "upper": "Upper-Intermediate", "fluent": "Fluent / Advanced"}


PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{8,}\d")
ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")  # rejected by openpyxl


def scrub(text):
    for rx, tag in PII:
        text = rx.sub(tag, text)
    # phone = 10+ digits; keeps year ranges like "2016 - 2020"
    text = PHONE.sub(lambda m: "[PHONE]" if sum(ch.isdigit() for ch in m.group()) >= 10 and not re.fullmatch(
        r"(19|20)\d\d\D+(19|20)\d\d", m.group()) else m.group(), text)
    return ILLEGAL.sub(" ", text)


def category(line):
    low = line.lower()
    if YEARS.search(low) or "experience" in low:
        return "experience"
    if any(w in low for w in ("degree", "bachelor", "master", "university", "education")):
        return "education"
    if "certif" in low:
        return "certification"
    if "english" in low or "language" in low and "programming" not in low:
        return "language"
    return "skill"


def text_requirements(desc):
    """Bullet-like lines inside a requirements section; falls back to bullets anywhere before an offer section."""
    lines = [l.strip(" \t-*•·–—▪✔✅●○►").strip() for l in re.split(r"[\n\r]+|(?<=[.;])\s+(?=[-•*])", desc)]
    out, inside, nice = [], False, False
    for l in lines:
        if not l:
            continue
        if STOP.search(l) and len(l) < 60:
            inside = False
            continue
        if HEADER.search(l) and len(l) < 60:
            inside, nice = True, bool(NICE.search(l))
            continue
        if inside and 12 <= len(l) <= 220:
            out.append((l, "nice" if nice or NICE.search(l) else "must"))
    return out[:MAX_TEXT_REQS]


def exp_years(v):
    m = re.match(r"(\d+)", str(v or ""))
    return float(m.group(1)) if m and m.group(1) != "0" else None


def requirements(job):
    reqs = [{"text": t, "kind": k, "category": category(t), "min_years": (float(m.group(1)) if (m := YEARS.search(t)) else None),
             "source": "job_text"} for t, k in text_requirements(job["Long Description"])]
    if (y := exp_years(job["Exp Years"])):
        reqs.append({"text": f"At least {y:g} years of experience as {job['Primary Keyword']} developer/engineer",
                     "kind": "must", "category": "experience", "min_years": y, "source": "job_metadata.Exp Years"})
    if (e := ENGLISH.get(str(job["English Level"]).lower())):
        reqs.append({"text": f"English level {e} or higher", "kind": "must", "category": "language", "min_years": None,
                     "source": "job_metadata.English Level"})
    return reqs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    raw, out = Path(a.raw), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cvs = pd.read_parquet(raw / "cvs.parquet")
    jobs = pd.read_parquet(raw / "jobs.parquet")
    cvs = cvs[(cvs.CV_lang == "en") & cvs.CV.str.len().between(400, 3000)].drop_duplicates("CV")
    jobs = jobs[(jobs["Long Description_lang"] == "en") & jobs["Long Description"].str.len().between(500, 4000)]
    jobs = jobs.drop_duplicates("Long Description")

    pairs, reqs = [], []
    for kw in KEYWORDS:
        c = cvs[cvs["Primary Keyword"] == kw].sample(PAIRS_PER_KEYWORD, random_state=SEED)
        j = jobs[jobs["Primary Keyword"] == kw]
        j = j[j["Long Description"].map(lambda d: len(text_requirements(d)) >= 2)].sample(PAIRS_PER_KEYWORD, random_state=SEED)
        for (_, cv), (_, job) in zip(c.iterrows(), j.iterrows()):
            pid = f"dj-{len(pairs) + 1:03d}"
            pairs.append({"pair_id": pid, "keyword": kw, "cv_id": cv["id"], "cv_text": scrub(cv["CV"]),
                          "cv_experience_years": cv["Experience Years"], "cv_english": cv["English Level"],
                          "job_id": job["id"], "job_title": scrub(job["Position"]), "job_text": scrub(job["Long Description"]),
                          "job_exp_years": job["Exp Years"], "job_english": job["English Level"]})
            for i, r in enumerate(requirements(job), 1):
                reqs.append({"pair_id": pid, "req_id": f"{pid}-r{i}", "keyword": kw, **r, "keep_requirement": "",
                             "decision": "", "basis": "", "evidence": "", "explanation": "", "labeller": "", "notes": ""})

    assert len({p["cv_id"] for p in pairs}) == len(pairs) and len({p["job_id"] for p in pairs}) == len(pairs)
    with open(out / "djinni_pairs.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(p, ensure_ascii=False, default=float) + "\n" for p in pairs)
    with open(out / "djinni_requirements_to_label.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in reqs)
    write_xlsx(out / "djinni_review.xlsx", pairs, reqs)
    print(f"pairs={len(pairs)} requirements={len(reqs)} by source={pd.Series([r['source'] for r in reqs]).value_counts().to_dict()}")


def write_xlsx(path, pairs, reqs):
    from openpyxl.styles import Alignment, Font
    from openpyxl.worksheet.datavalidation import DataValidation

    guide = pd.DataFrame({"How to label": [
        "1. Sheet 'pairs': read the CV (cv_text) and the job (job_text) of a pair_id.",
        "2. Sheet 'requirements': one row per candidate requirement of that job. keep_requirement = yes / no / edit "
        "(edit = fix the text in place). Drop vague or non-checkable lines (e.g. 'team player' if you cannot judge it).",
        "3. decision + basis must be one of: MET+supported | MISSING+contradicted | MISSING+not_documented | UNCERTAIN+ambiguous.",
        "4. evidence: copy 1-3 exact pieces of cv_text (character for character), separated by ' || '. Empty for not_documented.",
        "5. Use only the CV text. cv_experience_years / cv_english are platform metadata: do not quote them as evidence.",
        "6. explanation: one short sentence. labeller: your initials. notes: anything odd (PII left, broken text).",
        "7. If you see a real name, phone or e-mail that the scrubber missed, write PII in notes.",
        "Requirements are machine-split candidates, not labels. Nothing in this file is gold until a human fills it."]})
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        guide.to_excel(xw, sheet_name="README", index=False)
        pd.DataFrame(pairs).to_excel(xw, sheet_name="pairs", index=False)
        pd.DataFrame(reqs).to_excel(xw, sheet_name="requirements", index=False)
        ws = xw.sheets["requirements"]
        cols = {c.value: c.column_letter for c in ws[1]}
        n = len(reqs) + 1
        for col, opts in (("keep_requirement", "yes,no,edit"), ("decision", "MET,MISSING,UNCERTAIN"),
                          ("basis", "supported,contradicted,not_documented,ambiguous")):
            dv = DataValidation(type="list", formula1=f'"{opts}"', allow_blank=True)
            ws.add_data_validation(dv)
            dv.add(f"{cols[col]}2:{cols[col]}{n}")
        for name, widths in (("README", {"A": 140}), ("pairs", {"D": 80, "J": 90, "I": 30}),
                             ("requirements", {cols["text"]: 70, cols["evidence"]: 60, cols["explanation"]: 50})):
            sh = xw.sheets[name]
            for col, w in widths.items():
                sh.column_dimensions[col].width = w
            for row in sh.iter_rows(min_row=2):
                for cell in row:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
            for cell in sh[1]:
                cell.font = Font(bold=True)
            sh.freeze_panes = "A2"


if __name__ == "__main__":
    main()
