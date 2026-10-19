r"""Real-data baseline (T06): the 40 labelled Djinni CV x job pairs through the station API (same code as the n8n nodes).

Per pair: /reader -> /profile on the CV file, then /match for every gold requirement of the pair
(data/labels/gold/requirements_gold.csv: requirement text, kind, category, min_years; skill_terms empty, so the ESCO
query is the requirement text). Not from the Job Agent. Then: metrics per split (dev / test / all), the TEMP outcome
rule of T05 vs pairs_gold.csv (provisional), a Job Agent check on J1-J4, and ERRORS.md.

Usage: .venv\Scripts\python scripts\eval_real.py --out eval\results\<date>_real_baseline [--skip-run]
  --skip-run  recompute metrics / ERRORS.md from the saved rows.jsonl (no model call)
"""
import argparse
import csv
import json
import re
import time
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data/labels/gold"
CLASSES = ("MET", "MISSING", "UNCERTAIN")
W, V = {"must": 2, "nice": 1}, {"MET": 1, "UNCERTAIN": 0.5, "MISSING": 0}


def selected(r, select):
    """select: None = all, else a set of 'Pxx' (whole pair) or 'Pxx:rN' (one row)."""
    return select is None or r["pair_id"] in select or f"{r['pair_id']}:{r['req_id']}" in select


def run(api, out, select=None, judge=False, jobs=True):
    reqs = [r for r in csv.DictReader(open(GOLD / "requirements_gold.csv", encoding="utf-8")) if selected(r, select)]
    c = httpx.Client(base_url=api, timeout=1800)
    rows, profiles = [], {}
    pair_ids = sorted({r["pair_id"] for r in reqs})
    with open(out / "rows.jsonl", "w", encoding="utf-8") as f:
        for pid in pair_ids:
            pr = [r for r in reqs if r["pair_id"] == pid]
            cv = ROOT / "data/processed/cvs" / pr[0]["cv_file"]
            t = time.perf_counter()
            rd = c.post("/reader", files={"file": ("cv.txt", cv.read_bytes(), "text/plain")}).raise_for_status().json()
            prof = c.post("/profile", json={"cv_id": rd["cv_id"]}).raise_for_status().json()
            profiles[pid] = {"reader": rd, "profile": prof, "elapsed_s": round(time.perf_counter() - t, 2)}
            for r in pr:
                req = {"req_id": r["req_id"], "text": r["requirement"], "kind": r["kind"], "category": r["category"],
                       "skill_terms": [], "min_years": float(r["min_years"]) if r["min_years"] else None}
                m = c.post("/match", json={"cv_id": rd["cv_id"], "cv_text": prof["anonymised_text"],
                                           "requirement": req}).raise_for_status().json()
                if judge:  # T08: station 6 after /match, as in the n8n loop; adds its review reasons
                    m = c.post("/judge", json={"cv_text": prof["anonymised_text"], "requirement": req,
                                               "match": m}).raise_for_status().json()
                row = {"pair_id": pid, "job": r["job"], "split": r["split"], "req_id": r["req_id"], "kind": r["kind"],
                       "category": r["category"], "min_years": req["min_years"], "requirement": r["requirement"],
                       "gold": r["gold_decision"], "gold_quote": r["gold_quote"], "gold_source": r["source"],
                       "pred": m["decision"], "model_decision": m["model_decision"], "basis": m["basis"],
                       "quotes": m["evidence"], "explanation": m["explanation"], "review_reasons": m["review_reasons"],
                       "info_flags": m["info_flags"], "confidence": m["confidence"], "knowledge_refs": m["knowledge_refs"],
                       "lora_scale": m["model"]["lora_scale"], "model_latency_s": m["model"]["latency_s"],
                       "elapsed_s": m["elapsed_s"], "finish_reason": m["model"]["finish_reason"],
                       "judge_verdict": (m.get("judge") or {}).get("verdict"), "judge": m.get("judge")}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                rows.append(row)
            print(f"{pid}: profile {profiles[pid]['elapsed_s']}s, {len(pr)} requirements", flush=True)
    # the anonymised CV texts hold no identity; kept for the error analysis
    (out / "profiles.json").write_text(json.dumps(profiles, indent=1, ensure_ascii=False), encoding="utf-8")
    if not jobs:
        return
    jobs = {}
    for j in ("J1", "J2", "J3", "J4"):
        t = time.perf_counter()
        jobs[j] = c.post("/job", json={"job_text": (ROOT / f"data/processed/jobs/{j}.txt").read_text(encoding="utf-8"),
                                        "job_id": j}).raise_for_status().json()
        jobs[j]["wall_s"] = round(time.perf_counter() - t, 2)
    (out / "jobs.json").write_text(json.dumps(jobs, indent=1, ensure_ascii=False), encoding="utf-8")


def metrics(rows):
    gold, pred = [r["gold"] for r in rows], [r["pred"] for r in rows]
    f1 = {}
    for k in CLASSES:
        tp = sum(g == k and p == k for g, p in zip(gold, pred))
        fp = sum(g != k and p == k for g, p in zip(gold, pred))
        fn = sum(g == k and p != k for g, p in zip(gold, pred))
        pr, rc = (tp / (tp + fp) if tp + fp else 0.0), (tp / (tp + fn) if tp + fn else 0.0)
        f1[k] = round(2 * pr * rc / (pr + rc), 3) if pr + rc else 0.0
    false_met = sum(p == "MET" and g != "MET" for g, p in zip(gold, pred))
    met = [r for r in rows if r["pred"] == "MET"]
    return {"n": len(rows), "accuracy": round(sum(g == p for g, p in zip(gold, pred)) / len(rows), 3),
            "macro_f1": round(sum(f1.values()) / 3, 3), "f1_per_class": f1,
            "confusion_gold_x_pred": {g: {p: sum(x == g and y == p for x, y in zip(gold, pred)) for p in CLASSES} for g in CLASSES},
            "gold_counts": dict(Counter(gold)), "pred_counts": dict(Counter(pred)),
            "false_met": false_met, "false_met_rate_of_non_met_gold": round(false_met / max(1, sum(g != "MET" for g in gold)), 3),
            "false_met_share_of_pred_met": round(false_met / max(1, len(met)), 3),
            "met_with_verified_quote": round(sum(bool(r["quotes"]) for r in met) / max(1, len(met)), 3),
            "rows_with_review_reasons": sum(bool(r["review_reasons"]) for r in rows),
            "mean_model_latency_s": round(sum(r["model_latency_s"] for r in rows) / len(rows), 2),
            "mean_match_elapsed_s": round(sum(r["elapsed_s"] for r in rows) / len(rows), 2)}


def temp_outcome(pair_rows, profile):
    """The T05 TEMP rule (n8n 'TEMP outcome' node), on the Matcher output with the gold requirement list."""
    review = profile["reader"]["review_reasons"] + profile["profile"]["review_reasons"]
    review += [f"match:{r['req_id']}:{x}" for r in pair_rows for x in r["review_reasons"]]
    score = round(100 * sum(W[r["kind"]] * V[r["pred"]] for r in pair_rows) / sum(W[r["kind"]] for r in pair_rows))
    must_missing = [r["req_id"] for r in pair_rows if r["kind"] == "must" and r["pred"] == "MISSING"]
    outcome = "review" if review else "reject" if must_missing else "invite" if score >= 80 else "review"
    return outcome, score, review


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip().lower().rstrip(".;")


def job_check(jobs):
    draft = list(csv.DictReader(open(ROOT / "data/labels/requirements_draft.csv", encoding="utf-8")))
    out = {}
    for j, body in jobs.items():
        gold = [d for d in draft if d["job"] == j]
        agent = body["card"]["requirements"]
        aligned, used = [], set()
        for g in gold:
            src = norm(g["source_sentence"])
            hits = [a for a in agent if norm(a["evidence"]) and (norm(a["evidence"]) in src or src in norm(a["evidence"]))]
            used |= {a["req_id"] for a in hits}
            if hits:
                aligned.append({"gold": g["req_id"], "gold_kind": g["kind"], "agent": [a["req_id"] for a in hits],
                                "agent_kinds": sorted({a["kind"] for a in hits}),
                                "kind_agrees": all(a["kind"] == g["kind"] for a in hits)})
        out[j] = {"gold_requirements": len(gold), "agent_requirements": len(agent), "gold_found": len(aligned),
                  "gold_missed": [g["req_id"] for g in gold if g["req_id"] not in {x["gold"] for x in aligned}],
                  "agent_extra": [{"req_id": a["req_id"], "kind": a["kind"], "evidence": a["evidence"]}
                                  for a in agent if a["req_id"] not in used],
                  "must_nice_agree": sum(x["kind_agrees"] for x in aligned), "aligned": aligned,
                  "review_reasons": body["review_reasons"], "wall_s": body["wall_s"]}
    tot = {k: sum(v[k] for v in out.values()) for k in ("gold_requirements", "agent_requirements", "gold_found", "must_nice_agree")}
    tot["agent_extra"] = sum(len(v["agent_extra"]) for v in out.values())
    return out, tot


def gold_line(cv_text, quote):
    """The CV line holding the gold quote (or its first 40 characters)."""
    if not quote:
        return None
    for probe in (quote, quote[:40]):
        for line in cv_text.splitlines():
            if probe and probe in line:
                return line.strip()
    return None


def errors_md(rows, profiles):
    groups = {"false MET": [], "false MISSING": [], "missed UNCERTAIN": [], "other": []}
    for r in rows:
        if r["gold"] == r["pred"]:
            continue
        key = ("false MET" if r["pred"] == "MET" else "false MISSING" if r["pred"] == "MISSING" and r["gold"] == "MET"
               else "missed UNCERTAIN" if r["gold"] == "UNCERTAIN" else "other")
        groups[key].append(r)
    lines = ["# Matcher errors on the 40 real pairs (T06 baseline, real-GPU)", "",
             "Every disagreement between the Matcher (after validator v1) and `gold_decision`. Gold quotes are the "
             "labelers' and may not be exact CV substrings. **Cause** is my one-line guess from reading the CV, "
             "not a measurement. Splits: dev + test (nothing was tuned).", ""]
    for key, items in groups.items():
        lines += [f"## {key} ({len(items)})", ""]
        for r in items:
            anon = profiles[r["pair_id"]]["profile"]["anonymised_text"]
            q = " | ".join(e["quote"] for e in r["quotes"]) or "(no quote)"
            gl = gold_line(anon, r["gold_quote"])
            conf = (r["confidence"] or {}).get("normalized")
            lines += [f"- **{r['pair_id']} {r['req_id']}** ({r['split']}, {r['kind']}) {r['requirement']}",
                      f"  - gold **{r['gold']}** vs model **{r['pred']}** (model decision {r['model_decision']}, basis "
                      f"{r['basis']}; p={conf}; review: {', '.join(r['review_reasons']) or '-'})",
                      f"  - model quote: {q[:300]}",
                      f"  - CV line for gold: {gl[:300] if gl else ('(gold quote not found in the anonymised CV) ' + (r['gold_quote'][:200] or '(none)'))}",
                      "  - cause: CAUSE_TODO", ""]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8010")
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-run", action="store_true")
    ap.add_argument("--select", help="comma list of Pxx or Pxx:rN (default: all gold rows)")
    ap.add_argument("--judge", action="store_true", help="also call /judge after each /match (T08)")
    ap.add_argument("--no-jobs", action="store_true", help="skip the Job Agent check")
    ap.add_argument("--run-only", action="store_true", help="only call the API and save rows/profiles (no metrics)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if not a.skip_run:
        run(a.api, out, set(a.select.split(",")) if a.select else None, a.judge, not a.no_jobs)
    if a.run_only:
        return
    rows = [json.loads(line) for line in open(out / "rows.jsonl", encoding="utf-8")]
    profiles = json.loads((out / "profiles.json").read_text(encoding="utf-8"))
    summary = {"label": "real-GPU", "rows": len(rows),
               "matcher": {s: metrics([r for r in rows if s == "all" or r["split"] == s]) for s in ("dev", "test", "all")}}
    gold_pairs = {p["pair_id"]: p for p in csv.DictReader(open(GOLD / "pairs_gold.csv", encoding="utf-8"))}
    outcomes = []
    for pid in sorted(profiles):
        o, score, review = temp_outcome([r for r in rows if r["pair_id"] == pid], profiles[pid])
        outcomes.append({"pair_id": pid, "split": gold_pairs[pid]["split"], "gold_outcome": gold_pairs[pid]["gold_outcome"],
                         "temp_outcome": o, "score": score, "review_reasons": review})
    oc = {}
    for s in ("dev", "test", "all"):
        sel = [x for x in outcomes if s == "all" or x["split"] == s]
        oc[s] = {"n": len(sel), "agreement": round(sum(x["gold_outcome"] == x["temp_outcome"] for x in sel) / len(sel), 3),
                 "confusion_gold_x_temp": {g: {p: sum(x["gold_outcome"] == g and x["temp_outcome"] == p for x in sel)
                                               for p in ("invite", "review", "reject")} for g in ("invite", "review", "reject")},
                 "review_rate": round(sum(x["temp_outcome"] == "review" for x in sel) / len(sel), 3)}
    summary["temp_outcome_PROVISIONAL"] = {"note": "pairs_gold.csv outcomes are NOT human-checked yet and contain 0 invites",
                                           **oc, "per_pair": outcomes}
    if (out / "jobs.json").exists():
        per_job, tot = job_check(json.loads((out / "jobs.json").read_text(encoding="utf-8")))
        summary["job_agent"] = {"total": tot, "per_job": per_job}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    if not (out / "ERRORS.md").exists():  # the causes are written by hand afterwards: never overwrite them
        (out / "ERRORS.md").write_text(errors_md(rows, profiles), encoding="utf-8")
    for s in ("dev", "test", "all"):
        m = summary["matcher"][s]
        print(f"{s}: n {m['n']} acc {m['accuracy']} macroF1 {m['macro_f1']} F1 {m['f1_per_class']} falseMET {m['false_met']}")
    print("TEMP outcome (provisional):", {s: (oc[s]["agreement"], oc[s]["review_rate"]) for s in oc})
    if "job_agent" in summary:
        print("Job Agent:", summary["job_agent"]["total"])


if __name__ == "__main__":
    main()
