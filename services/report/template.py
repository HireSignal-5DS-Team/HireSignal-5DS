"""Template report (station 7 fallback and baseline, T12): built only from the record, so it passes the fact checker
by construction (tested)."""
from __future__ import annotations

from .record import _flag_texts

WORD = {"MET": "met", "MISSING": "missing", "UNCERTAIN": "uncertain"}


def render(record: dict) -> dict:
    reqs = record["requirements"]
    must = [r for r in reqs if r["kind"] == "must"]
    met = [r for r in must if r["decision"] == "MET"]
    missing = [r for r in must if r["decision"] == "MISSING"]
    unsure = [r for r in must if r["decision"] == "UNCERTAIN"]
    o = record["outcome"]
    first = {"invite": "The candidate is invited to the next step.",
             "reject": "The candidate is rejected.",
             "review": "This case goes to a recruiter for review."}[o]
    summary = [first, f"{len(met)} of {len(must)} must-have requirements are met; the score is {record['score']}."]
    if missing:
        summary.append("Missing must-haves: " + "; ".join(r["text"] for r in missing) + ".")
    if unsure:
        summary.append("Unclear must-haves: " + "; ".join(r["text"] for r in unsure) + ".")
    if o == "review" and record["gate_reasons"]:
        summary.append("Reason for review: " + "; ".join(record["gate_reasons"][:3]) + ".")
    lines = []
    for r in reqs:
        quote = r["quotes"][0] if r["quotes"] and r["decision"] == "MET" else ""
        tail = f"CV: {quote}" if quote else "not found in CV" if r["decision"] == "MISSING" else "unclear in the CV"
        lines.append({"req_id": r["req_id"], "decision": r["decision"], "quote": quote,  # T13: decision word first
                      "line": f"{WORD[r['decision']].capitalize()}: {r['text']} ({r['kind']}; {tail})"})
    letter = ""
    if record.get("decided_by") == "human":  # T13: a recruiter decided after review
        if o == "invite":
            letter = ("Dear candidate,\n\nThank you for your application. After a review by our team, we would like "
                      "to invite you to the next step of the process.\n\nKind regards")
        elif o == "reject":
            reasons = missing or unsure
            letter = ("Dear candidate,\n\nThank you for your application. After a review by our team, we will not "
                      "move forward with it" + (", because your CV does not clearly show these required points: "
                                                 + "; ".join(r["text"] for r in reasons) if reasons else "")
                      + ".\n\nIf you have questions about this decision, simply reply to this message.\n\nKind regards")
    elif o == "invite":
        letter = ("Dear candidate,\n\nThank you for your application. Your profile meets the requirements of this "
                  "position, and we would like to invite you to the next step of the process.\n\nKind regards")
    elif o == "reject":
        letter = ("Dear candidate,\n\nThank you for your application. After checking your CV against the "
                  "requirements of this position, we will not move forward, because your CV does not show these "
                  "required points: " + "; ".join(r["text"] for r in missing) + ".\n\nThis decision was prepared "
                  "with an automated system. You have the right to request a human review of this decision "
                  "(GDPR Art. 22): simply reply to this message.\n\nKind regards")
    return {"recruiter_summary": " ".join(summary), "requirements": lines, "candidate_letter": letter,
            "flags_for_recruiter": sorted(_flag_texts(record))}
