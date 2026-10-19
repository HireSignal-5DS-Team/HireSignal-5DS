r"""T10 Part D: does the decision survive a phone photo / a scan? (test only: the 5 labelled L CVs)

For each L CV and each image condition (close photo, hard photo, scan) and each Reader setup, the setup's text goes
through the real chain of the station API: /reader (text upload) -> /profile -> confirmed requirement card J1-J4 ->
per requirement /rag/search (V6) -> /match -> /judge -> /outcome (the same input the n8n "Outcome input" node builds).
The Reader's image-quality review reasons (services.reader.reader.quality_reasons, as in read_cv) are added to the
pair review reasons. The digital PDF (L0x.pdf, text layer) goes through the same chain as reference (b).
Compares with (a) the gold outcome, (b) the digital outcome, (c) requirement-level agreement with gold.

Needs: llama-server + station API running (scripts/start_stack.ps1); Ollama is not needed (texts are cached by
scripts/eval_multimodal.py). Usage:
  .venv\Scripts\python scripts\eval_multimodal_chain.py --mm eval\results\2026-10-18_multimodal --vision qwen2.5vl_3b__v1
      [--early qwen2.5vl_3b__v1] --out eval\results\2026-10-18_multimodal\chain
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from eval_multimodal import ground_truth, items, load, page_text, save  # noqa: E402
from services.reader import multimodal as mm  # noqa: E402
from services.reader.reader import quality_reasons  # noqa: E402

GOLD = ROOT / "data/labels/gold"


def cases(its):
    """One case per (L CV, condition): its items (the two L04 page photos form one CV)."""
    out = {}
    for it in its:
        if it["split"] == "test":
            out.setdefault((it["source"][:3], it["condition"]), []).append(it)
    return out


def setup_text(mm_dir, setup, its, vision, early):
    """(text, review reasons, details) of one setup for the items of one case, from the cached runs."""
    texts, confs, details = [], [], []
    for it in sorted(its, key=lambda x: x["id"]):
        o = load(mm_dir / "ocr" / f"{it['id']}.json")
        confs += [p["conf"] for p in o["pages"] if p["conf"] is not None]
        if setup == "ocr":
            texts.append(page_text(o))
        elif setup == "vision":
            v = load(mm_dir / "vision" / vision / f"{it['id']}.json")
            texts.append(page_text(v))
            details += [{"unclear_share": mm.unclear_share(p["text"]), "vision_truncated": p.get("done_reason") == "length"}
                        for p in v["pages"]]
        elif setup == "late":
            f = load(mm_dir / "late" / f"{it['id']}.json")
            texts.append(f["text"])
            details += [{"fusion": p["stats"]} for p in f["pages"]]
        elif setup == "early":
            v = load(mm_dir / "early" / early / f"{it['id']}.json")
            texts.append(page_text(v))
            details += [{"unclear_share": mm.unclear_share(p["text"]), "vision_truncated": p.get("done_reason") == "length"}
                        for p in v["pages"]]
    text = "\n\n".join(texts)
    conf = round(sum(confs) / len(confs), 1) if confs else None
    return text, quality_reasons(text, conf, details), {"ocr_confidence": conf}


def run_chain(c, text, job, reader_reasons):
    r = c.post("/reader", files={"file": ("cv.txt", text.encode("utf-8"), "text/plain")}).raise_for_status().json()
    p = c.post("/profile", json={"cv_id": r["cv_id"]}).raise_for_status().json()
    card = json.loads((ROOT / f"data/processed/jobs/{job}_requirements.json").read_text(encoding="utf-8"))
    reqs, results = card["requirements"], []
    cv_text = p["anonymised_text"]
    for req in reqs:
        req = {k: req.get(k) for k in ("req_id", "text", "kind", "category", "skill_terms", "min_years")}
        rag = c.post("/rag/search", json={"requirement": req, "cv_text": cv_text}).raise_for_status().json()
        m = c.post("/match", json={"cv_text": cv_text, "requirement": req, "knowledge_refs": rag["knowledge_refs"],
                                   "knowledge": rag["retriever"]}).raise_for_status().json()
        m = c.post("/judge", json={"cv_text": cv_text, "requirement": req, "match": m}).raise_for_status().json()
        results.append((req, m))
    body = {"requirements": [{"req_id": m["req_id"], "kind": q["kind"], "decision": m["decision"],
                              "review_reasons": m["review_reasons"], "info_flags": m["info_flags"],
                              "category": q["category"], "min_years": q["min_years"],
                              "evidence_years": m.get("evidence_years"),
                              "confidence": (m.get("confidence") or {}).get("normalized"),
                              "judge": {"verdict": m["judge"]["verdict"], "nli_probs": m["judge"].get("nli_probs")}
                              if m.get("judge") else None} for q, m in results],
            "pair_review_reasons": reader_reasons + r["review_reasons"] + p["review_reasons"],
            "pair_info_flags": r["info_flags"] + p["info_flags"]}
    o = c.post("/outcome", json=body).raise_for_status().json()
    return {"outcome": o["outcome"], "rule": o["rule"], "score": o["score"], "reasons": o["reasons"],
            "pair_review_reasons": body["pair_review_reasons"],
            "decisions": {m["req_id"]: m["decision"] for _, m in results}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mm", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--vision", required=True)
    ap.add_argument("--early")
    ap.add_argument("--setups", default="ocr,vision,late,early")
    ap.add_argument("--api", default="http://127.0.0.1:8010")
    a = ap.parse_args()
    mm_dir, out = Path(a.mm), Path(a.out)
    setups = [s for s in a.setups.split(",") if s != "early" or a.early]
    its = items()
    gold_pairs = {p["pair_id"]: p for p in csv.DictReader(open(GOLD / "pairs_gold.csv", encoding="utf-8"))}
    gold_req = {}
    for r in csv.DictReader(open(GOLD / "requirements_gold.csv", encoding="utf-8")):
        gold_req.setdefault(r["pair_id"], {})[r["req_id"]] = r["gold_decision"]
    c = httpx.Client(base_url=a.api, timeout=900)
    rows = []
    by_cv = {}
    for (src, cond), group in sorted(cases(its).items()):
        by_cv.setdefault(src, []).append((cond, group))
    for src, conds in by_cv.items():
        pair, job = conds[0][1][0]["pair"], conds[0][1][0]["job"]
        runs = [("digital", "digital PDF", None)] + [(cond, s, group) for cond, group in conds for s in setups]
        for cond, setup, group in runs:
            p = out / f"{src}__{cond.replace(' ', '_')}__{setup.replace(' ', '_')}.json"
            res = load(p)
            if res is None:
                if group is None:
                    gt_item = next(it for it in its if it["source"].startswith(src))
                    text = ground_truth(gt_item | {"pages": list(range(1, 3)) if src == "L04" else [1]})
                    reasons, extra = [], {}
                else:
                    text, reasons, extra = setup_text(mm_dir, setup, group, a.vision, a.early)
                res = {"cv": src, "pair": pair, "job": job, "condition": cond, "setup": setup,
                       "items": [g["id"] for g in group] if group else [f"{src}.pdf"], "reader_reasons": reasons,
                       **extra, **run_chain(c, text, job, reasons)}
                save(p, res)
            g = gold_req[pair]
            res["req_agree_gold"] = f"{sum(res['decisions'].get(k) == v for k, v in g.items())}/{len(g)}"
            res["gold_outcome"] = gold_pairs[pair]["gold_outcome"]
            rows.append(res)
            print(src, pair, cond, setup, res["outcome"], "gold", res["gold_outcome"], "req", res["req_agree_gold"],
                  res["reader_reasons"], flush=True)
    digital = {r["cv"]: r for r in rows if r["setup"] == "digital PDF"}
    for r in rows:
        r["digital_outcome"] = digital[r["cv"]]["outcome"]
        r["req_agree_digital"] = (f"{sum(r['decisions'].get(k) == v for k, v in digital[r['cv']]['decisions'].items())}"
                                  f"/{len(digital[r['cv']]['decisions'])}")
    summary = {}
    for s in setups:
        rs = [r for r in rows if r["setup"] == s]
        same = sum(r["outcome"] == r["digital_outcome"] for r in rs)
        safe = sum(r["outcome"] != r["digital_outcome"] and r["outcome"] == "review" for r in rs)
        wrong = [f"{r['cv']} {r['condition']}: {r['outcome']} (digital {r['digital_outcome']})" for r in rs
                 if r["outcome"] != r["digital_outcome"] and r["outcome"] != "review"]
        summary[s] = {"cases": len(rs), "same_as_digital": same, "safe_review_instead": safe, "unsafe_changes": wrong,
                      "same_as_gold": sum(r["outcome"] == r["gold_outcome"] for r in rs),
                      "req_agree_gold": f"{sum(int(r['req_agree_gold'].split('/')[0]) for r in rs)}/"
                                        f"{sum(int(r['req_agree_gold'].split('/')[1]) for r in rs)}",
                      "req_agree_digital": f"{sum(int(r['req_agree_digital'].split('/')[0]) for r in rs)}/"
                                           f"{sum(int(r['req_agree_digital'].split('/')[1]) for r in rs)}"}
    dg = list(digital.values())
    summary["digital PDF"] = {"cases": len(dg), "same_as_gold": sum(r["outcome"] == r["gold_outcome"] for r in dg),
                              "req_agree_gold": f"{sum(int(r['req_agree_gold'].split('/')[0]) for r in dg)}/"
                                                f"{sum(int(r['req_agree_gold'].split('/')[1]) for r in dg)}"}
    save(out / "summary.json", {"label": "real-GPU (station API chain: Qwen3-4B + LoRA, DeBERTa Judge, V6 RAG, T08b gate)",
                                "vision": a.vision, "early": a.early, "summary": summary, "rows": rows})
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
