r"""T09 Part D: effect of each RAG variant on the Matcher (364 gold rows, 52 pairs, real-GPU) and on the T08b gate.

V0 = the T08b rows (BM25 over chunking A, query = the whole requirement sentence), reused, not re-run.
V1..V6 = /match (with confidence) -> /judge through the station API, with knowledge refs computed here:
  V1 BM25 + skill terms (chunking A)        V2 dense all-MiniLM-L6-v2 (chunking A) + skill terms
  V3 hybrid (BM25 + MiniLM, RRF)            V4 V3 + cross-encoder ms-marco-MiniLM-L-6-v2 on the top 20
  V5 V4 + ESCO graph expansion              V6 V2, but no knowledge block when every skill term is already in the CV
Skill terms: data/processed/jobs/J<n>_requirements.json (scripts/add_skill_terms.py). The CV text is never a query.
Choice on dev only: Matcher macro-F1, then gate false rejects, then the simpler variant; test is report-only.
Rows are appended to <out>/rows_<V>.jsonl and a rerun resumes where it stopped.

Usage: .venv\Scripts\python scripts\eval_rag_matcher.py --out eval\results\<date>_rag_matcher [--variants V1,V2] [--report-only]
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from eval_real import metrics  # noqa: E402
from rag.retrieval import EscoRetriever, terms_in_cv  # noqa: E402
from services.matcher.validate import evidence_years  # noqa: E402
from services.outcome.gate import decide  # noqa: E402

EXTRA = ROOT / "eval/results/2026-10-18_extra_pairs"
GOLD = ROOT / "data/labels/gold"
VARIANTS = {
    "V1": dict(chunking="A", search="bm25"),
    "V2": dict(chunking="A", search="dense", embed="all-MiniLM-L6-v2"),
    "V3": dict(chunking="A", search="hybrid", embed="all-MiniLM-L6-v2"),
    "V4": dict(chunking="A", search="hybrid", embed="all-MiniLM-L6-v2", reranker="ms-marco-MiniLM-L-6-v2"),
    "V5": dict(chunking="A", search="hybrid", embed="all-MiniLM-L6-v2", reranker="ms-marco-MiniLM-L-6-v2", graph=True),
    "V6": dict(chunking="A", search="dense", embed="all-MiniLM-L6-v2"),
}
SIMPLER = ["V0", "V1", "V2", "V6", "V3", "V4", "V5"]
GATE = dict(t_invite=85, pair_flags="info", judge_met_max_conf=0.999)  # T08b, chosen on dev
# T06 ERRORS.md "alias / buried-term" misses
ALIAS_ROWS = {("P12", "r2"), ("P13", "r1"), ("P15", "r1"), ("P06", "r3"), ("P20", "r4"), ("P21", "r4")}


def cards():
    out = {}
    for j in ("J1", "J2", "J3", "J4"):
        for r in json.loads((ROOT / f"data/processed/jobs/{j}_requirements.json").read_text(encoding="utf-8"))["requirements"]:
            out[(j, r["req_id"])] = r
    return out


def run_variant(name, api, out, profiles, gold_rows, card, device):
    path = out / f"rows_{name}.jsonl"
    done = {(r["pair_id"], r["req_id"]) for r in map(json.loads, open(path, encoding="utf-8"))} if path.exists() else set()
    retr = EscoRetriever(device=device, **VARIANTS[name])
    c = httpx.Client(base_url=api, timeout=900)
    with open(path, "a", encoding="utf-8") as f:
        for g in gold_rows:
            key = (g["pair_id"], g["req_id"])
            if key in done:
                continue
            cv_text = profiles[g["pair_id"]]["profile"]["anonymised_text"]
            cr = card[(g["job"], g["req_id"])]
            req = {"req_id": g["req_id"], "text": g["requirement"], "kind": g["kind"], "category": g["category"],
                   "skill_terms": cr["skill_terms"], "min_years": float(g["min_years"]) if g["min_years"] else None}
            t = time.perf_counter()
            skipped = name == "V6" and terms_in_cv(req, cv_text)
            refs = [] if skipped else retr.lookup(req, k=3)
            rag_s = time.perf_counter() - t
            m = c.post("/match", json={"cv_text": cv_text, "requirement": req, "knowledge_refs": refs,
                                       "knowledge": retr.name + (" +only-when-missing" if name == "V6" else "")}).raise_for_status().json()
            m = c.post("/judge", json={"cv_text": cv_text, "requirement": req, "match": m}).raise_for_status().json()
            row = {"pair_id": g["pair_id"], "job": g["job"], "split": g["split"], "req_id": g["req_id"], "kind": g["kind"],
                   "category": g["category"], "min_years": req["min_years"], "requirement": g["requirement"],
                   "skill_terms": req["skill_terms"], "gold": g["gold_decision"], "pred": m["decision"],
                   "model_decision": m["model_decision"], "basis": m["basis"], "quotes": m["evidence"],
                   "review_reasons": m["review_reasons"], "info_flags": m["info_flags"], "confidence": m["confidence"],
                   "judge": m["judge"], "judge_verdict": m["judge"]["verdict"], "knowledge_refs": m["knowledge_refs"],
                   "rag_skipped": skipped, "rag_s": round(rag_s, 4), "elapsed_s": m["elapsed_s"],
                   "lora_scale": m["model"]["lora_scale"], "finish_reason": m["model"]["finish_reason"]}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
    print(f"{name}: done", flush=True)


def report(rows, profiles, gold_pairs):
    unc = [r for r in rows if r["gold"] == "UNCERTAIN"]
    out = {}
    for sp in ("dev", "test", "all"):
        sel = [r | {"model_latency_s": r.get("model_latency_s", r.get("elapsed_s", 0))}
               for r in rows if sp == "all" or r["split"] == sp]
        m = metrics(sel)
        res = {}
        for pid in sorted({r["pair_id"] for r in sel}):
            reqs = [{"req_id": r["req_id"], "kind": r["kind"], "decision": r["pred"], "review_reasons": r["review_reasons"],
                     "info_flags": r.get("info_flags") or [], "category": r["category"],
                     "confidence": (r.get("confidence") or {}).get("normalized"), "judge": r.get("judge"),
                     "min_years": r["min_years"], "evidence_years": evidence_years([q["quote"] for q in r["quotes"]])
                     if r["min_years"] and r["quotes"] else None} for r in rows if r["pair_id"] == pid]
            pr = profiles[pid]
            res[pid] = decide(reqs, pr["reader"]["review_reasons"] + pr["profile"]["review_reasons"], **GATE).outcome
        gp = {p: gold_pairs[p]["gold_outcome"] for p in res}
        su = [r for r in unc if sp == "all" or r["split"] == sp]
        out[sp] = {"n": m["n"], "accuracy": m["accuracy"], "macro_f1": m["macro_f1"], "f1_per_class": m["f1_per_class"],
                   "false_met": m["false_met"], "uncertain_recall": round(sum(r["pred"] == "UNCERTAIN" for r in su) / max(1, len(su)), 3),
                   "alias_errors_fixed": f"{sum(r['pred'] == r['gold'] for r in sel if (r['pair_id'], r['req_id']) in ALIAS_ROWS)}"
                                         f"/{sum((r['pair_id'], r['req_id']) in ALIAS_ROWS for r in sel)}",
                   "mean_match_s": round(sum(r.get("elapsed_s", 0) for r in sel) / len(sel), 2),
                   "mean_rag_ms": round(1000 * sum(r.get("rag_s", 0) for r in sel) / len(sel), 1),
                   "rag_skipped": sum(bool(r.get("rag_skipped")) for r in sel),
                   "gate": {"false_invites": sum(res[p] == "invite" and gp[p] != "invite" for p in res),
                            "false_rejects": sum(res[p] == "reject" and gp[p] != "reject" for p in res),
                            "invites_found": sum(res[p] == "invite" and gp[p] == "invite" for p in res),
                            "review_rate": round(sum(res[p] == "review" for p in res) / len(res), 3)}}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--api", default="http://127.0.0.1:8010")
    ap.add_argument("--variants", default="V1,V2,V3,V4,V5,V6")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    profiles = json.loads((EXTRA / "profiles_all_52.json").read_text(encoding="utf-8"))
    gold_rows = list(csv.DictReader(open(GOLD / "requirements_gold.csv", encoding="utf-8")))
    gold_pairs = {p["pair_id"]: p for p in csv.DictReader(open(GOLD / "pairs_gold.csv", encoding="utf-8"))}
    card = cards()
    if not a.report_only:
        for v in a.variants.split(","):
            run_variant(v, a.api, out, profiles, gold_rows, card, a.device)
    results = {"V0": report([json.loads(x) for x in open(EXTRA / "rows_all_52_variant4.jsonl", encoding="utf-8")],
                            profiles, gold_pairs)}
    for v in VARIANTS:
        p = out / f"rows_{v}.jsonl"
        if p.exists():
            rows = [json.loads(x) for x in open(p, encoding="utf-8")]
            if len(rows) == len(gold_rows):
                results[v] = report(rows, profiles, gold_pairs)
    ranked = sorted(results, key=lambda v: (-results[v]["dev"]["macro_f1"], results[v]["dev"]["gate"]["false_rejects"],
                                            SIMPLER.index(v)))
    chosen = ranked[0]
    if results[chosen]["dev"]["macro_f1"] <= results["V0"]["dev"]["macro_f1"] and chosen != "V0":
        chosen = "V0"  # nothing beats the current setup on dev: keep it
    summary = {"label": "real-GPU (Matcher + Judge through the station API; retrieval on cuda)", "variants": VARIANTS,
               "gate_settings": GATE, "results": results, "dev_ranking": ranked, "chosen_on_dev": chosen}
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    for v, r in results.items():
        print(v, " | ".join(f"{sp}: mF1 {r[sp]['macro_f1']} F1 {r[sp]['f1_per_class']} fMET {r[sp]['false_met']} UNCrec "
                            f"{r[sp]['uncertain_recall']} alias {r[sp]['alias_errors_fixed']} gate FI {r[sp]['gate']['false_invites']} "
                            f"FR {r[sp]['gate']['false_rejects']} rev {r[sp]['gate']['review_rate']}" for sp in ("dev", "test")))
    print("chosen on dev:", chosen)


if __name__ == "__main__":
    main()
