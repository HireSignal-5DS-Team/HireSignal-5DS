"""Re-score saved raw generations through a deterministic output adapter (matcher/output_adapters.py) without new
inference. The source run is left untouched; the result is a new run directory <src>__<adapter>.

  python -m benchmark.rescore --run qwen2.5-0.5b+kushal-lora-rag-val --adapter schema_repair
"""
import argparse
import json
import shutil

from matcher import output_adapters
from matcher.knowledge import NoKnowledge, RagKnowledge
from matcher.schemas import CV, Requirement
from matcher.validate import find_span, parse_model_output, validate

from . import metrics
from .compare import ROOT
from .run import DATA, read_jsonl


def rescore(run, adapter, root=ROOT):
    src = root / run
    cfg = json.loads((src / "config.json").read_text())
    cases = {c["case_id"]: c for c in read_jsonl(DATA / f"{cfg['split']}.jsonl")}
    knowledge = RagKnowledge() if cfg["knowledge"] == "rag.bm25" else NoKnowledge()
    out = root / f"{run}__{adapter}"
    if out.exists():
        shutil.rmtree(out)  # derived data only: fully recomputed from the source run
    out.mkdir()
    recs = []
    for r in read_jsonl(src / "predictions.jsonl"):
        c = cases[r["case_id"]]
        cv = CV(**c["cv"])
        req = Requirement(**next(x for x in c["job"]["requirements"] if x["req_id"] == r["req_id"]))
        raw = output_adapters.schema_repair(r["raw"]) if adapter == "schema_repair" else \
            output_adapters.kushal_native(r["raw"], req.skill_terms)
        ans = parse_model_output(raw)
        res = validate(ans, cv, req, knowledge.lookup(req, k=cfg["k"]))
        quotes = ans.evidence if ans else []
        recs.append({**r, "adapted_raw": raw, "decision": res.decision, "basis": res.basis,
                     "model_decision": res.model_decision, "parsed": ans is not None, "raw_quotes": quotes,
                     "raw_quotes_valid": sum(find_span(cv.text, q) is not None for q in quotes),
                     "evidence": res.evidence, "evidence_spans": res.evidence_spans,
                     "needs_human_review": res.needs_human_review, "review_reasons": res.review_reasons})
    (out / "predictions.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in recs))
    cfg = {**cfg, "run_id": out.name, "derived_from": run, "output_adapter": adapter,
           "note": "post-hoc deterministic output adapter on the saved raw generations; no new inference"}
    cfg["backend"] = {**cfg["backend"], "output_adapter": adapter}
    (out / "config.json").write_text(json.dumps(cfg, indent=2) + "\n")
    m = metrics.compute(recs)
    src_m = json.loads((src / "metrics.json").read_text())
    m["peak_rss_mb"], m["load_seconds"] = src_m.get("peak_rss_mb"), src_m.get("load_seconds")
    (out / "metrics.json").write_text(json.dumps(m, indent=2) + "\n")
    (out / "metrics.md").write_text(metrics.to_markdown(m, f"{out.name} (post-hoc adapter `{adapter}`, no new inference)"))
    return m


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--adapter", required=True, choices=["schema_repair", "kushal_native"])
    a = ap.parse_args()
    m = rescore(a.run, a.adapter)
    print(json.dumps({"n": m["n"], "macro_f1": round(m["final"]["macro_f1"], 4), "raw_macro_f1": round(m["raw_model"]["macro_f1"], 4),
                      "false_met": m["final"]["false_met_rate"], "json_validity": m["json_schema_validity"]}))
