r"""Skill terms for the gold requirements (T09 Part D fix): the Job Agent's own skill_terms (T06 /job run on J1-J4,
eval/results/2026-10-18_real_baseline/jobs.json), aligned by source sentence, kept only when the term is written in the
gold requirement text (case-insensitive). No term -> [] (the RAG query stays the requirement text).
Writes skill_terms into data/processed/jobs/J<n>_requirements.json.
Usage: .venv\Scripts\python scripts\add_skill_terms.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from eval_real import norm  # noqa: E402

JOBS = ROOT / "eval/results/2026-10-18_real_baseline/jobs.json"


def terms_for(req, agent_reqs):
    src = norm(req["evidence"])
    hits = [a for a in agent_reqs if norm(a["evidence"]) and (norm(a["evidence"]) in src or src in norm(a["evidence"]))]
    return [t for t in dict.fromkeys(t for a in hits for t in a["skill_terms"]) if t.lower() in req["text"].lower()]


def main():
    jobs = json.loads(JOBS.read_text(encoding="utf-8"))
    for j in ("J1", "J2", "J3", "J4"):
        p = ROOT / f"data/processed/jobs/{j}_requirements.json"
        card = json.loads(p.read_text(encoding="utf-8"))
        for r in card["requirements"]:
            r["skill_terms"] = terms_for(r, jobs[j]["card"]["requirements"])
        card["skill_terms_source"] = "Job Agent terms (T06 run) aligned by source sentence, kept if in the requirement text"
        p.write_text(json.dumps(card, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(j, [(r["req_id"], r["skill_terms"]) for r in card["requirements"]])


if __name__ == "__main__":
    main()
