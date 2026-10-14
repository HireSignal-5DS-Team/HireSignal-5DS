"""Human review of the frozen evaluation queries, without overwriting the original gold labels.

    python rag/review.py export                       # -> eval/review/review_sheet.csv + review_sheet.md
    python rag/review.py apply --reviewer "Name"      # reads the filled CSV
        -> eval/queries_reviewed.jsonl  (original eval/queries.jsonl is never modified)
        -> eval/review/changelog.md     (every decision, old vs new gold)
    python rag/evaluate.py --queries eval/queries_reviewed.jsonl --models e5-small bge-m3
        -> eval/results_reviewed/       (original eval/results/ is kept for comparison)

Reviewer columns: decision = ACCEPT | CORRECT | REJECT; corrected_gold = new gold list when CORRECT
(ESCO: URIs separated by " | "; job: verbatim quotes separated by " || "); notes = free text.
"""
import argparse
import csv
import json
from pathlib import Path

from corpus import load_esco, load_jobs

HERE = Path(__file__).parent
QUERIES = HERE / "eval/queries.jsonl"
REVIEWED = HERE / "eval/queries_reviewed.jsonl"
DIR = HERE / "eval/review"
SHEET = DIR / "review_sheet.csv"
RANKINGS = HERE / "eval/results/rankings.jsonl"
SUGGEST_FROM = ("structure", "e5-small", "dense")  # default configuration; its non-gold top-3 are offered as candidates
COLUMNS = ["qid", "source_type", "lang", "query", "expected_answer", "gold", "supporting_passage", "source_reference",
           "alternative_candidates", "decision", "corrected_gold", "notes"]
SEP = {"esco": " | ", "job": " || "}


def _load():
    queries = [json.loads(line) for line in open(QUERIES, encoding="utf-8") if line.strip()]
    jobs = {j["doc_id"]: j for j in load_jobs()}
    esco = {e["doc_id"]: e for e in load_esco()}
    return queries, jobs, esco


def _context(text, quote, width=200):
    i = text.find(quote)
    return f"...{text[max(0, i - width):i]}[[{quote}]]{text[i + len(quote):i + len(quote) + width]}..."


def export():
    queries, jobs, esco = _load()
    top3 = {}
    for line in open(RANKINGS, encoding="utf-8"):
        r = json.loads(line)
        if (r["strategy"], r["model"], r["mode"]) == SUGGEST_FROM and r["setting"] in ("scoped", "esco", "none"):
            top3[r["qid"]] = r["top3"]
    rows = []
    for q in queries:
        t = q["type"]
        if t == "esco":
            gold, answer = SEP["esco"].join(q["gold_uris"]), " / ".join(q["gold_labels"])
            passage = "\n".join(f"{esco[u]['title']}: {esco[u]['text']}" for u in q["gold_uris"])
            ref = "ESCO v1.1.x (en), concept URI(s) in gold column"
            alts = [esco[c]["title"] + " <" + c + ">" for c in top3.get(q["qid"], []) if c not in q["gold_uris"]]
        elif t == "job":
            job = jobs[q["job_id"]]
            gold, answer = SEP["job"].join(q["gold_quotes"]), "the gold quote below, from this posting"
            passage = "\n".join(_context(job["text"], g) for g in q["gold_quotes"])
            n = job["text"].count(q["gold_quotes"][0])
            ref = f"{job['title']} ({job['organisation']}), {job['source_url']}; occurs {n}x in the posting"
            alts = []
            for cid in top3.get(q["qid"], []):
                c = next((x for x in _job_chunks(job) if x["chunk_id"] == cid), None)
                if c and not any(g in job["text"][c["start"]:c["end"]] for g in q["gold_quotes"]):
                    alts.append(f"{cid} [{c['section']}]: {job['text'][c['start']:c['start'] + 160]}...")
        else:
            gold, answer, passage = "", "no_match: no ESCO concept should be returned", ""
            ref = "ESCO subset (concept absent; see docs/esco_coverage.md)"
            alts = [esco[c]["title"] + " <" + c + ">" for c in top3.get(q["qid"], [])]
        rows.append({"qid": q["qid"], "source_type": "job description" if t == "job" else t, "lang": q.get("lang", "en"),
                     "query": q["query"], "expected_answer": answer, "gold": gold, "supporting_passage": passage,
                     "source_reference": ref,
                     "alternative_candidates": "\n".join(alts) and "SYSTEM SUGGESTIONS, NOT VERIFIED:\n" + "\n".join(alts),
                     "decision": "", "corrected_gold": "", "notes": ""})
    DIR.mkdir(parents=True, exist_ok=True)
    with open(SHEET, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel shows accents correctly
        w = csv.DictWriter(f, COLUMNS)
        w.writeheader()
        w.writerows(rows)
    md = ["# Query review sheet (read-only view; fill in review_sheet.csv)\n"]
    for r in rows:
        md += [f"## {r['qid']} ({r['source_type']}, {r['lang']})", f"**Query:** {r['query']}  ",
               f"**Expected answer:** {r['expected_answer']}  ", f"**Gold:** `{r['gold'] or '(none)'}`  ",
               f"**Source:** {r['source_reference']}\n", "**Supporting passage** (gold in [[ ]]):\n",
               "> " + (r["supporting_passage"] or "(none)").replace("\n", "\n> ") + "\n",
               "**Alternative candidates:**\n", "> " + (r["alternative_candidates"] or "(none)").replace("\n", "\n> ") + "\n",
               "**Decision:** ACCEPT / CORRECT / REJECT  \n**Corrected gold:**  \n**Notes:**\n"]
    (DIR / "review_sheet.md").write_text("\n".join(md), encoding="utf-8")
    print(f"exported {len(rows)} queries to {SHEET} and review_sheet.md")


def _job_chunks(job):
    from chunking import structure_chunks
    return structure_chunks(job)


WORDING = "Suggested query wording:"


def apply(reviewer, sheet=SHEET, provenance="human review"):
    """CORRECT may change the gold (corrected_gold), the question (notes: 'Suggested query wording: ...'), or both.
    A no-answer query corrected with ESCO URIs becomes an ESCO query. REJECT drops the query from the reviewed set
    and keeps it in eval/review/rejected_queries.jsonl."""
    queries, jobs, esco = _load()
    sheet_rows = {r["qid"]: r for r in csv.DictReader(open(sheet, encoding="utf-8-sig"))}
    extra = set(sheet_rows) - {q["qid"] for q in queries}
    errors = [f"{qid}: not in queries.jsonl" for qid in sorted(extra)]
    out, rejected = [], []
    log = [f"# Review changelog\n", f"Reviewer: {reviewer}. Provenance: {provenance}. Source sheet: `{Path(sheet).name}`.\n",
           "| qid | decision | gold change | old gold | new gold | old question | new question | notes |",
           "|---|---|---|---|---|---|---|---|"]
    for q in queries:
        r = sheet_rows.get(q["qid"])
        decision = (r or {}).get("decision", "").strip().upper()
        if decision not in ("ACCEPT", "CORRECT", "REJECT"):
            errors.append(f"{q['qid']}: decision must be ACCEPT, CORRECT or REJECT, got {decision!r}")
            continue
        notes, raw_gold = r["notes"].strip(), r["corrected_gold"].strip()
        wording = notes.split(WORDING, 1)[1].strip() if WORDING in notes else ""
        qtype = "esco" if q["type"] == "none" and decision == "CORRECT" and raw_gold else q["type"]
        key = {"esco": "gold_uris", "job": "gold_quotes"}.get(qtype)
        old, new, change = q.get(key, []) if key else [], None, "kept"
        if decision == "CORRECT":
            if not raw_gold and not wording:
                errors.append(f"{q['qid']}: CORRECT needs corrected_gold or '{WORDING}' in notes")
                continue
            if raw_gold:
                new = [g.strip() for g in raw_gold.split(SEP[qtype].strip()) if g.strip()]
                bad = [g for g in new if (g not in esco if qtype == "esco" else g not in jobs[q["job_id"]]["text"])]
                if bad:
                    errors.append(f"{q['qid']}: corrected gold not an ESCO URI of the subset / not verbatim in the posting: {bad}")
                    continue
                change = "replaced" if q["type"] == qtype else f"replaced ({q['type']} -> {qtype})"
        if decision == "REJECT":
            change = "query excluded"
        log.append(f"| {q['qid']} | {decision} | {change} | {'; '.join(old)[:90]} | {'; '.join(new)[:90] if new else ''} "
                   f"| {q['query'] if wording and decision == 'CORRECT' else ''} | {wording if decision == 'CORRECT' else ''} "
                   f"| {notes.replace('|', '/')} |")
        audit = {"labelled_by": provenance, "verified_by": reviewer, "review_decision": decision, "review_notes": notes}
        if decision == "REJECT":
            rejected.append({**q, **audit})
            continue
        reviewed = {**q, **audit}
        if decision == "CORRECT" and wording:
            reviewed["query"], reviewed["query_original"] = wording, q["query"]
        if new:
            reviewed.update({"type": qtype, key: new, "gold_original": old, "type_original": q["type"]})
            if qtype == "esco":
                reviewed["gold_labels"] = [esco[u]["title"] for u in new]
        out.append(reviewed)
    if errors:  # all-or-nothing: a half-applied review would silently mix reviewed and unreviewed labels
        raise SystemExit("review not applied:\n" + "\n".join(errors))
    for path, rows in ((REVIEWED, out), (DIR / "rejected_queries.jsonl", rejected)):
        with open(path, "w", encoding="utf-8") as f:
            for q in rows:
                f.write(json.dumps(q, ensure_ascii=False) + "\n")
    (DIR / "changelog.md").write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"{len(out)} queries kept, {len(rejected)} rejected -> {REVIEWED}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["export", "apply"])
    ap.add_argument("--reviewer")
    ap.add_argument("--sheet", default=SHEET, type=Path)
    ap.add_argument("--provenance", default="human review", help="how the review was produced, recorded per query")
    a = ap.parse_args()
    if a.command == "export":
        export()
    else:
        if not a.reviewer:
            ap.error("apply needs --reviewer")
        apply(a.reviewer, a.sheet, a.provenance)
