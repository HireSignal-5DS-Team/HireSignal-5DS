"""Live smoke test of the fine-tuned Matcher pipeline on a few val cases (default 3). Needs both llama.cpp servers
(scripts/live_smoke.sh starts and stops them). Checks provenance, schema, citations and review routing, including a
forced-fallback run; writes run artefacts; exit code 1 if any check fails.

  python scripts/live_smoke.py --out benchmark/results/live_smoke/<run-id> [--cases val-000,val-001,val-002] [--judge]

Output: report-<case>.json / .md, predictions.jsonl (one line per requirement, gold shown for reading only),
smoke.json (checks + summary + provenance). 3 cases are a smoke test, NOT an accuracy measurement.
"""
import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark.run import DATA, read_jsonl  # noqa: E402
from matcher.factory import build, model_provenance  # noqa: E402
from matcher.pipeline import write_report  # noqa: E402
from matcher.schemas import MatchReport  # noqa: E402

COSMETIC = {"think_block", "code_fence"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cases", default="val-000,val-001,val-002")
    ap.add_argument("--judge", action="store_true", help="also run the NLI Judge (needs torch + the DeBERTa model)")
    a = ap.parse_args()
    env = dict(os.environ)
    env.setdefault("HS_RAG", "bm25")
    if not a.judge:
        env["HS_JUDGE"] = "off"
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    pin, _, _ = model_provenance(env)
    cases = {c["case_id"]: c for c in read_jsonl(DATA / "val.jsonl")}
    pipe = build(env)
    checks, preds, reports = {}, [], {}
    t0 = time.time()
    for cid in a.cases.split(","):
        c = cases[cid]
        out = pipe.run(c["cv"], c["job"])
        reports[cid] = out
        (out_dir / f"report-{cid}.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
        (out_dir / f"report-{cid}.md").write_text(write_report(out))
        for x in out["requirements"]:
            preds.append({"case_id": cid, "req_id": x["req_id"], "gold": c["gold"][x["req_id"]]["decision"],
                          "final_decision": x["final_decision"], "model_decision": x["model_decision"],
                          "basis": x["basis"], "evidence": x["evidence"], "rag_refs": x["rag_refs"],
                          "review": x["requires_human_review"], "review_reasons": x["review_reasons"],
                          "latency_s": (x.get("matcher_call") or {}).get("latency_s"), "provenance": x["provenance"]})
    with open(out_dir / "predictions.jsonl", "w") as f:
        for p in preds:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    rows = [(cid, x) for cid, o in reports.items() for x in o["requirements"]]
    prov = [x["provenance"] for _, x in rows]
    try:
        for o in reports.values():
            MatchReport.model_validate(o["match_report"])
        checks["match_report_validates_frozen_schema"] = True
    except Exception as e:  # noqa: BLE001
        checks["match_report_validates_frozen_schema"] = f"{type(e).__name__}: {e}"[:300]
    try:
        import jsonschema

        schema = json.loads((ROOT / "matcher/json_schemas/MatchReport.schema.json").read_text())
        for o in reports.values():
            jsonschema.validate(o["match_report"], schema)
        checks["match_report_validates_json_schema_file"] = True
    except ImportError:
        checks["match_report_validates_json_schema_file"] = "skipped: jsonschema not installed"
    except Exception as e:  # noqa: BLE001
        checks["match_report_validates_json_schema_file"] = f"{type(e).__name__}: {e}"[:300]
    checks["no_mock_backend"] = not any(p.get("MOCK") for p in prov)
    checks["every_result_answered_by_lora_primary"] = all(p.get("answered_by") == "primary" for p in prov)
    checks["served_alias_verified"] = all(p.get("alias_verified") is True for p in prov)
    checks["adapter_is_pinned_revision"] = all(p.get("adapter") == pin["adapter"] for p in prov)
    checks["base_revision_and_weights_recorded"] = all(p.get("base_revision") == pin["base_revision"]
                                                       and p.get("weights") == pin["weights"] for p in prov)
    checks["prompt_and_knowledge_recorded"] = all(p.get("prompt_id") == "p1" and p.get("knowledge_provider") for p in prov)
    checks["rag_enabled"] = all(o["knowledge"] != "none" for o in reports.values())
    checks["citations_equal_rag_refs"] = all(x["rag_refs"] == [c["source_id"] for c in x["citations"]] for _, x in rows)
    checks["evidence_spans_verbatim"] = all(cases[cid]["cv"]["text"][s:e] == q for cid, x in rows
                                            for q, (s, e) in zip(x["evidence"], x["evidence_spans"]))
    checks["unparseable_or_repaired_routed_to_review"] = all(
        x["requires_human_review"] for _, x in rows
        if x["model_decision"] is None or set(x["provenance"]["repairs"]) - COSMETIC)
    checks["must_missing_routed_to_review"] = all(x["requires_human_review"] for _, x in rows
                                                  if x["kind"] == "must" and x["final_decision"] == "MISSING")

    # forced fallback: primary unreachable -> the base model answers, provenance says so, result goes to review
    fb_env = {**env, "HS_MATCHER_URL": "http://127.0.0.1:9/v1", "HS_MAX_RETRIES": "0", "HS_JUDGE": "off"}
    c0 = cases[a.cases.split(",")[0]]
    fb = build(fb_env).run(c0["cv"], {**c0["job"], "requirements": c0["job"]["requirements"][:1]})
    (out_dir / "forced-fallback.json").write_text(json.dumps(fb, indent=2, ensure_ascii=False) + "\n")
    fx = fb["requirements"][0]
    checks["forced_fallback_provenance_and_review"] = (fx["provenance"]["answered_by"] == "fallback"
                                                       and fx["provenance"]["adapter"] is None
                                                       and fx["provenance"]["alias_verified"] is True
                                                       and "matcher:fallback_model_used" in fx["review_reasons"])

    lat = sorted(p["latency_s"] for p in preds if p["latency_s"] is not None)
    summary = {
        "label": ("LIVE (llama.cpp servers started by scripts/live_smoke.sh)" if os.environ.get("HS_SMOKE_SERVERS") == "started"
                  else "UNVERIFIED SERVERS (not started by scripts/live_smoke.sh; may be fakes)")
                 + " - smoke test, not an accuracy measurement",
        "cases": a.cases.split(","), "n_requirements": len(preds), "wall_s": round(time.time() - t0, 1),
        "parsed_strict": sum(not set(p["provenance"]["repairs"]) - COSMETIC and p["model_decision"] is not None for p in preds),
        "parsed_after_repair": sum(bool(set(p["provenance"]["repairs"]) - COSMETIC) and p["model_decision"] is not None for p in preds),
        "unparseable": sum(p["model_decision"] is None for p in preds),
        "finish_reason_length": sum(p["provenance"].get("finish_reason") == "length" for p in preds),
        "review": sum(p["review"] for p in preds),
        "agree_with_gold_info_only": sum(p["final_decision"] == p["gold"] for p in preds),
        "latency_p50_s": statistics.median(lat) if lat else None,
        "latency_max_s": lat[-1] if lat else None,
    }
    ok = all(v is True or (isinstance(v, str) and v.startswith("skipped")) for v in checks.values())
    result = {"ok": ok, "checks": checks, "summary": summary, "backend": next(iter(reports.values()))["backend"],
              "env": {k: env.get(k) for k in ("HS_RAG", "HS_MATCHER_URL", "HS_FALLBACK_URL", "HS_JUDGE", "HIRESIGNAL_RAG_DIR")}}
    (out_dir / "smoke.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"ok": ok, "failed": {k: v for k, v in checks.items() if v is not True}, "summary": summary}, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
