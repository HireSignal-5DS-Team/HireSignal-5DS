"""Evaluate one arm on the 202 val requirements: same prompts (prompt_tuning/data/val_prompts.jsonl, identical to
finetune/data/sft_val.jsonl), same RAG refs, greedy decoding, max 192 new tokens, the production validator and
benchmark.metrics. Writes predictions.jsonl in the benchmark/run.py record format, so benchmark tooling can read it.
Resumable: existing (case_id, req_id) keys are skipped; a config change under the same run id is refused.

  python -m prompt_tuning.evaluate --arm base --device cuda --dtype float16 --run-id base-fp16-val
  python -m prompt_tuning.evaluate --arm soft_prompt --soft-prompt prompt_tuning/runs/sp-base-v1/soft_prompt \\
      --device cuda --dtype float16 --run-id sp-base-v1-fp16-val

--label marks the run: MEASURED (the real 4B model), SMOKE (tiny/random model, plumbing only). The label is written
into metrics.json and metrics.md and must be carried into any table.
"""
import argparse
import json
import os
import platform
import resource
import sys
import time
from pathlib import Path

from .common import BENCH, MANIFEST, RESULTS, VAL_PROMPTS, BASE, BASE_REVISION, config_hash, read_jsonl, sha256


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", required=True, choices=["base", "lora", "soft_prompt", "lora_soft_prompt"])
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--revision", default=BASE_REVISION)
    ap.add_argument("--lora")
    ap.add_argument("--lora-revision")
    ap.add_argument("--soft-prompt", help="directory written by train_soft_prompt (…/soft_prompt)")
    ap.add_argument("--prompts", default=str(VAL_PROMPTS))
    ap.add_argument("--gold", default=str(BENCH / "val.jsonl"))
    ap.add_argument("--manifest", default=str(MANIFEST))
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out-root", default=str(RESULTS))
    ap.add_argument("--limit", type=int, default=0, help="first N prompts only (0 = all 202)")
    ap.add_argument("--max-new-tokens", type=int, default=192)
    ap.add_argument("--dtype", default="float32", choices=["float32", "bfloat16", "float16"])
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--label", default="MEASURED", choices=["MEASURED", "SMOKE"])
    ap.add_argument("--seed", type=int, default=13, help="recorded; decoding is greedy")
    a = ap.parse_args(argv)
    a.revision = a.revision or None  # '' = local model dir, no revision
    a.argv = list(sys.argv[1:] if argv is None else argv)
    return a


def refuse_test(prompts_path, prompts, manifest):
    assert "test" not in Path(prompts_path).stem.lower(), "refusing a prompts file named like the locked test split"
    if Path(manifest).exists():
        test_ids = set(json.loads(Path(manifest).read_text())["test_case_ids"])
        hit = [p["case_id"] for p in prompts if p["case_id"] in test_ids]
        assert not hit, f"refusing: prompts from the locked test split, e.g. {hit[:3]}"


def peak_rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Linux: KiB


def run_config(a, backend):
    return {"arm": a.arm, "backend": backend.info() | {"load_seconds": None}, "prompts_sha256": sha256(a.prompts),
            "gold_sha256": sha256(a.gold), "limit": a.limit, "max_new_tokens": a.max_new_tokens, "dtype": a.dtype,
            "device": a.device, "label": a.label}


def record(p, case, raw, latency, backend_call):
    from matcher.schemas import CV, KnowledgeRef, Requirement
    from matcher.validate import find_span, parse_model_output, validate

    cv = CV(**case["cv"])
    req = Requirement(**next(r for r in case["job"]["requirements"] if r["req_id"] == p["req_id"]))
    ans = parse_model_output(raw)
    res = validate(ans, cv, req, [KnowledgeRef(**x) for x in p["refs"]])
    g = case["gold"][p["req_id"]]
    quotes = ans.evidence if ans else []
    return {"case_id": p["case_id"], "req_id": p["req_id"], "tags": g["tags"], "gold_decision": g["decision"],
            "gold_basis": g["basis"], "gold_evidence": g["evidence"],
            "gold_spans": [find_span(cv.text, q) for q in g["evidence"]], "decision": res.decision, "basis": res.basis,
            "model_decision": res.model_decision, "parsed": ans is not None, "raw": raw, "raw_quotes": quotes,
            "raw_quotes_valid": sum(find_span(cv.text, q) is not None for q in quotes), "evidence": res.evidence,
            "evidence_spans": res.evidence_spans, "needs_human_review": res.needs_human_review,
            "review_reasons": res.review_reasons, "rag_refs": res.rag_refs, "latency_s": round(latency, 4),
            "call": backend_call}


def run(a):
    import torch

    from benchmark import metrics

    from .backend import SoftPromptBackend

    prompts = read_jsonl(a.prompts)[: a.limit or None]
    refuse_test(a.prompts, prompts, a.manifest)
    cases = {c["case_id"]: c for c in read_jsonl(a.gold)}
    torch.manual_seed(a.seed)
    if a.device == "cpu":
        torch.set_num_threads(os.cpu_count() or 1)
    if a.device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    be = SoftPromptBackend(a.arm, a.base, a.revision, a.lora, a.lora_revision, a.soft_prompt, a.dtype, a.device,
                           a.max_new_tokens)
    out = Path(a.out_root) / a.run_id
    out.mkdir(parents=True, exist_ok=True)
    cfg = run_config(a, be)
    cfg["config_hash"] = config_hash(cfg)
    cfg_path = out / "config.json"
    if cfg_path.exists():
        prev = json.loads(cfg_path.read_text())
        if prev["config_hash"] != cfg["config_hash"]:
            raise SystemExit(f"{out} was produced with another configuration (hash {prev['config_hash'][:12]}); "
                             f"use a new --run-id")
    import peft
    import transformers

    full = {**cfg, "backend": be.info(), "git_commit": os.popen("git rev-parse HEAD 2>/dev/null").read().strip() or None,
            "hardware": {"platform": platform.platform(), "python": sys.version.split()[0], "cpu_count": os.cpu_count(),
                         "torch": torch.__version__, "transformers": transformers.__version__, "peft": peft.__version__,
                         "cuda": torch.cuda.is_available(),
                         "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None},
            "command": " ".join(["python -m prompt_tuning.evaluate", *a.argv])}
    cfg_path.write_text(json.dumps(full, indent=2) + "\n")

    pred = out / "predictions.jsonl"
    if pred.exists():
        raw_b = pred.read_bytes()
        if raw_b and not raw_b.endswith(b"\n"):
            pred.write_bytes(raw_b[: raw_b.rfind(b"\n") + 1])
    done = {(r["case_id"], r["req_id"]) for r in read_jsonl(pred)} if pred.exists() else set()
    with pred.open("a", encoding="utf-8") as f:
        for i, p in enumerate(prompts):
            if (p["case_id"], p["req_id"]) in done:
                continue
            t0 = time.perf_counter()
            raw = be.generate_messages(p["messages"])
            lat = time.perf_counter() - t0
            f.write(json.dumps(record(p, cases[p["case_id"]], raw, lat, be.last_call), ensure_ascii=False) + "\n")
            f.flush()
            if (i + 1) % 10 == 0:
                print(f"{i + 1}/{len(prompts)}", flush=True)

    keys = {(p["case_id"], p["req_id"]) for p in prompts}
    recs = [r for r in read_jsonl(pred) if (r["case_id"], r["req_id"]) in keys]
    m = metrics.compute(recs)
    m.update(label=a.label, arm=a.arm, config_hash=cfg["config_hash"], peak_rss_mb=round(peak_rss_mb(), 1),
             peak_vram_mb=round(torch.cuda.max_memory_allocated() / 2**20, 1) if a.device == "cuda" else None,
             load_seconds=round(be.load_seconds, 2), backend=be.info(),
             uncertain_rate=sum(r["decision"] == "UNCERTAIN" for r in recs) / len(recs))
    (out / "metrics.json").write_text(json.dumps(m, indent=2) + "\n")
    title = (f"{a.label} {a.run_id}: arm={a.arm} | {a.base}" + (f" + {a.lora} (merged)" if a.lora else "") +
             (f" + soft prompt {a.soft_prompt}" if a.soft_prompt else "") + f" | transformers {a.dtype} {a.device}")
    (out / "metrics.md").write_text(metrics.to_markdown(m, title) +
                                    f"\nPeak RSS: {m['peak_rss_mb']} MB; peak VRAM: {m['peak_vram_mb']} MB; "
                                    f"load: {m['load_seconds']} s; config hash `{cfg['config_hash']}`\n")
    print(json.dumps({"label": a.label, "run_id": a.run_id, "arm": a.arm, "n": m["n"],
                      "macro_f1": round(m["final"]["macro_f1"], 4), "false_met_rate": m["final"]["false_met_rate"],
                      "json_validity": m["json_schema_validity"]}))
    return m


if __name__ == "__main__":
    run(parse_args())
