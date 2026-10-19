r"""Confirmed requirement cards for J1-J4 (T08b): the gold requirement list as a recruiter-confirmed job card.

Writes data/processed/jobs/J<n>_requirements.json in the /job card shape (job_id, title, requirements with req_id, text,
kind, category, min_years, skill_terms, evidence = the job sentence). Source: data/labels/gold/requirements_gold.csv
(kind as in gold, so J2 r6 is nice) + data/labels/requirements_draft.csv (source sentences).
Usage: .venv\Scripts\python scripts\make_job_cards.py
"""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    gold = list(csv.DictReader(open(ROOT / "data/labels/gold/requirements_gold.csv", encoding="utf-8")))
    draft = {(d["job"], d["req_id"]): d for d in csv.DictReader(open(ROOT / "data/labels/requirements_draft.csv", encoding="utf-8"))}
    for job in ("J1", "J2", "J3", "J4"):
        text = (ROOT / f"data/processed/jobs/{job}.txt").read_text(encoding="utf-8")
        title = re.search(r"^Position: (.+)$", text, re.M).group(1).strip()
        reqs, seen = [], set()
        for g in gold:
            if g["job"] != job or g["req_id"] in seen:
                continue
            seen.add(g["req_id"])
            evidence = draft[(job, g["req_id"])]["source_sentence"]
            assert evidence in text, (job, g["req_id"])
            reqs.append({"req_id": g["req_id"], "text": g["requirement"], "kind": g["kind"], "category": g["category"],
                         "min_years": float(g["min_years"]) if g["min_years"] else None, "skill_terms": [],
                         "evidence": evidence})
        reqs.sort(key=lambda r: int(r["req_id"][1:]))
        card = {"job_id": job, "title": title, "confirmed_by": "recruiter (sample: the gold requirement list)",
                "requirements": reqs}
        (ROOT / f"data/processed/jobs/{job}_requirements.json").write_text(json.dumps(card, indent=1, ensure_ascii=False) + "\n",
                                                                         encoding="utf-8")
        print(job, title, len(reqs), "requirements,", sum(r["kind"] == "must" for r in reqs), "must")


if __name__ == "__main__":
    main()
