"""Run base or base+adapter on a set of Matcher prompts with greedy decoding, the project's validator and metrics.

Ported from feature/qwen3-4b-finetune-handoff@2b7d42e (finetuning/eval_val.py); generalised to any cases/prompts
file so the same code scores the 202 val requirements and the real Djinni eval split, with or without RAG (A-D).
Evaluation only; refuses the sealed test file.

  python -m finetuning.eval_matcher --cases benchmark/data/val.jsonl --prompts finetuning/data/eval/val_rag_prompts.jsonl       --run-id A_base_none --out /kaggle/working/eval [--adapter /kaggle/working/qwen3-4b-hs-lora/adapter]
Output per run: predictions.jsonl (same fields as benchmark/run.py), metrics.json, metrics.md. Resumable.
"""
import argparse
import json
import time
from pathlib import Path

from benchmark import metrics
from benchmark.run import read_jsonl
from matcher.schemas import CV, KnowledgeRef, Requirement
from matcher.validate import find_span, parse_model_output, validate



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="Qwen/Qwen3-4B-Instruct-2507")
    ap.add_argument("--revision")
    ap.add_argument("--adapter")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-new-tokens", type=int, default=192)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    assert "test" not in Path(a.cases).stem.lower() and "test" not in Path(a.prompts).stem.lower(), "sealed test needs explicit approval"
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    tok = AutoTokenizer.from_pretrained(a.base, revision=a.revision)
    q = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16)
    model = AutoModelForCausalLM.from_pretrained(a.base, revision=a.revision, quantization_config=q, device_map={"": 0})
    if a.adapter:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, a.adapter)
    model.eval()
    cases = {c["case_id"]: c for c in read_jsonl(a.cases)}
    prompts = read_jsonl(a.prompts)[: a.limit or None]
    out = Path(a.out) / a.run_id
    out.mkdir(parents=True, exist_ok=True)
    pred = out / "predictions.jsonl"
    done = {(r["case_id"], r["req_id"]) for r in read_jsonl(pred)} if pred.exists() else set()
    with pred.open("a", encoding="utf-8") as f:
        for p in prompts:
            if (p["case_id"], p["req_id"]) in done:
                continue
            c = cases[p["case_id"]]
            cv = CV(**c["cv"])
            req = Requirement(**next(r for r in c["job"]["requirements"] if r["req_id"] == p["req_id"]))
            text = tok.apply_chat_template(p["messages"], tokenize=False, add_generation_prompt=True)
            ids = tok(text, return_tensors="pt").to(model.device)
            t0 = time.perf_counter()
            with torch.no_grad():
                o = model.generate(**ids, max_new_tokens=a.max_new_tokens, do_sample=False, pad_token_id=tok.eos_token_id)
            raw = tok.decode(o[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)
            lat = time.perf_counter() - t0
            ans = parse_model_output(raw)
            res = validate(ans, cv, req, [KnowledgeRef(**x) for x in p["refs"]])
            g = c["gold"][p["req_id"]]
            quotes = ans.evidence if ans else []
            f.write(json.dumps({
                "case_id": p["case_id"], "req_id": p["req_id"], "tags": g["tags"], "gold_decision": g["decision"],
                "gold_basis": g["basis"], "gold_evidence": g["evidence"], "gold_spans": [find_span(cv.text, x) for x in g["evidence"]],
                "decision": res.decision, "basis": res.basis, "model_decision": res.model_decision, "parsed": ans is not None,
                "raw": raw, "raw_quotes": quotes, "raw_quotes_valid": sum(find_span(cv.text, x) is not None for x in quotes),
                "evidence": res.evidence, "evidence_spans": res.evidence_spans, "needs_human_review": res.needs_human_review,
                "review_reasons": res.review_reasons, "rag_refs": res.rag_refs, "latency_s": round(lat, 4)}, ensure_ascii=False) + "\n")
            f.flush()
    m = metrics.compute(read_jsonl(pred))
    (out / "metrics.json").write_text(json.dumps({"base": a.base, "revision": a.revision, "adapter": a.adapter,
                                                  "quantization": "bnb nf4 4-bit, fp16 compute", "cases": a.cases, "prompts": a.prompts, **m}, indent=2) + "\n")
    (out / "metrics.md").write_text(metrics.to_markdown(m, f"{a.run_id}: {a.base} + {a.adapter or 'no adapter'} (Kaggle, 4-bit)"))
    print(json.dumps({"run": a.run_id, "n": m["n"], "macro_f1": round(m["final"]["macro_f1"], 4),
                      "false_met": m["final"]["false_met_rate"], "json_validity": m["json_schema_validity"]}))


if __name__ == "__main__":
    main()
