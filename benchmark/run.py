"""Run one Matcher configuration on a benchmark split. Resumable: predictions.jsonl is appended per requirement and
existing (case_id, req_id) keys are skipped on restart. Every configuration uses the same prompt, data and
greedy decoding, so runs are comparable.

  python -m benchmark.run --backend lexical --split val --knowledge rag --run-id lexical-rag-val
  python -m benchmark.run --backend transformers --model Qwen/Qwen2.5-0.5B-Instruct \\
      --revision 7ae557604adf67be50417f59c2c2f167def9a775 --split val --knowledge rag --run-id q25-rag-val
  # the locked test split needs --i-understand-test-is-locked (final confirmation of an already-selected config)
"""
import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

from matcher.agent import Matcher
from matcher.backends import LexicalBaseline, MockBackend
from matcher.knowledge import NoKnowledge, RagKnowledge
from matcher.schemas import CV, Job
from matcher.validate import find_span

from . import metrics

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "benchmark/data"


def read_jsonl(p):
    return [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]


def gold_backend(cases, uncertain=False):
    gold = {(c["cv"]["cv_id"], r): g for c in cases for r, g in c["gold"].items()}

    def fn(task):
        if uncertain:
            return json.dumps({"decision": "UNCERTAIN", "basis": "ambiguous", "evidence": [], "explanation": "mock"})
        g = gold[(task.cv.cv_id, task.req.req_id)]
        return json.dumps({"decision": g["decision"], "basis": g["basis"], "evidence": g["evidence"], "explanation": "mock gold"})
    return MockBackend(fn, label="MOCK-uncertain" if uncertain else "MOCK-gold (sanity check, not a model)")


def make_backend(a, cases):
    if a.backend == "lexical":
        return LexicalBaseline()
    if a.backend in ("mock_gold", "mock_uncertain"):
        return gold_backend(cases, a.backend == "mock_uncertain")
    if a.backend == "seq2seq":
        from matcher.backends_extra import Seq2SeqBackend

        return Seq2SeqBackend(a.model, revision=a.revision, max_new_tokens=a.max_new_tokens, device=a.device, dtype=a.dtype)
    if a.backend == "openai":
        from matcher.backends_api import OpenAICompatBackend

        return OpenAICompatBackend(base_url=a.base_url, model=a.model, max_tokens=a.max_new_tokens, provider=a.provider,
                                   timeout=a.timeout)
    if a.backend == "fermi":
        from matcher.backends_extra import FermiBackend

        return FermiBackend(a.fermi_repo, a.fermi_base, device=a.device)
    from matcher.backends import TransformersBackend

    return TransformersBackend(a.model, adapter_id=a.adapter, revision=a.revision, adapter_revision=a.adapter_revision,
                               max_new_tokens=a.max_new_tokens, device=a.device, dtype=a.dtype,
                               prompt_variant=a.prompt_variant, constrained=a.constrained)


def hardware():
    hw = {"platform": platform.platform(), "python": sys.version.split()[0], "cpu_count": os.cpu_count()}
    try:
        import psutil

        hw["ram_gb"] = round(psutil.virtual_memory().total / 2**30, 1)
    except ImportError:
        pass
    try:
        import torch
        import transformers

        hw.update(torch=torch.__version__, transformers=transformers.__version__, cuda=torch.cuda.is_available(),
                  torch_threads=torch.get_num_threads())
        if torch.cuda.is_available():
            hw["gpu"] = torch.cuda.get_device_name(0)
    except ImportError:
        pass
    return hw


def peak_rss_mb():
    try:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Linux: KiB
    except ImportError:  # Windows
        import psutil

        return psutil.Process().memory_info().peak_wset / 2**20


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        return None


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", required=True, choices=["lexical", "mock_gold", "mock_uncertain", "transformers", "seq2seq", "fermi", "openai"])
    ap.add_argument("--base-url", help="openai backend: OpenAI-compatible /v1 endpoint (local llama.cpp server or hosted API)")
    ap.add_argument("--provider", default="local", help="openai backend: 'local' or a hosted provider name (cost bookkeeping)")
    ap.add_argument("--timeout", type=float, default=300.0, help="openai backend: per-call timeout in seconds")
    ap.add_argument("--fermi-repo", help="local snapshot of Zerflyne/FERMI-0.8B (its fermi/ package is imported)")
    ap.add_argument("--fermi-base", help="local snapshot of Qwen/Qwen3.5-0.8B")
    ap.add_argument("--model")
    ap.add_argument("--revision")
    ap.add_argument("--adapter")
    ap.add_argument("--adapter-revision")
    ap.add_argument("--split", default="val", choices=["train", "val", "test"])
    ap.add_argument("--knowledge", default="rag", choices=["rag", "none"])
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0, help="first N cases only (0 = all)")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out-root", default=str(ROOT / "benchmark/results"))
    ap.add_argument("--max-new-tokens", type=int, default=192)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--dtype", default="float32")
    ap.add_argument("--data-dir", default=str(DATA))
    ap.add_argument("--i-understand-test-is-locked", action="store_true")
    ap.add_argument("--prompt-variant", default="p1", choices=["p1", "p1_oneshot", "kushal_native"],
                    help="adapter study only; p1 is the Matcher prompt")
    ap.add_argument("--constrained", action="store_true", help="JSON-schema constrained decoding (transformers backend)")
    a = ap.parse_args(argv)
    if a.backend in ("transformers", "seq2seq", "openai") and not a.model:
        ap.error(f"--model is required for --backend {a.backend}")
    if a.backend == "fermi" and not (a.fermi_repo and a.fermi_base):
        ap.error("--fermi-repo and --fermi-base are required for --backend fermi")
    if a.split == "test" and not a.i_understand_test_is_locked:
        ap.error("the test split is LOCKED; pass --i-understand-test-is-locked only for the final confirmation run")
    return a


def run(a):
    data_dir = Path(a.data_dir)
    cases = read_jsonl(data_dir / f"{a.split}.jsonl")[: a.limit or None]
    if a.split == "test":
        print("WARNING: running on the LOCKED test split. Do not use these numbers for model selection.", flush=True)
    out = Path(a.out_root) / a.run_id
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((data_dir / "MANIFEST.json").read_text())
    knowledge = RagKnowledge() if a.knowledge == "rag" else NoKnowledge()
    t0 = time.perf_counter()
    backend = make_backend(a, cases)
    cfg = {"run_id": a.run_id, "split": a.split, "limit": a.limit, "knowledge": knowledge.name, "k": a.k,
           "backend": backend.info(), "dataset_version": manifest["version"],
           "dataset_sha256": manifest["splits"][a.split]["sha256"], "git_commit": git_commit(), "hardware": hardware(),
           "load_seconds": round(time.perf_counter() - t0, 2)}
    cfg_path = out / "config.json"
    if cfg_path.exists():  # resume only into an identical configuration
        prev = json.loads(cfg_path.read_text())
        for key in ("split", "knowledge", "k", "dataset_sha256"):
            if prev[key] != cfg[key]:
                raise SystemExit(f"{out} was produced with {key}={prev[key]!r}; use a new --run-id")
        for key in ("model_id", "revision", "adapter_id", "adapter_revision", "backend"):
            if prev["backend"].get(key) != cfg["backend"].get(key):
                raise SystemExit(f"{out} was produced with backend {key}={prev['backend'].get(key)!r}; use a new --run-id")
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")

    pred_path = out / "predictions.jsonl"
    if pred_path.exists():  # a killed run can leave a half-written last line: drop it before appending
        raw = pred_path.read_bytes()
        if raw and not raw.endswith(b"\n"):
            pred_path.write_bytes(raw[: raw.rfind(b"\n") + 1])
    done ={(r["case_id"], r["req_id"]) for r in read_jsonl(pred_path)} if pred_path.exists() else set()
    matcher = Matcher(backend, knowledge, k=a.k)
    from matcher.validate import parse_model_output

    with pred_path.open("a", encoding="utf-8") as f:
        for c in cases:
            cv, job = CV(**c["cv"]), Job(**c["job"])
            for req in job.requirements:
                if (c["case_id"], req.req_id) in done:
                    continue
                res, info = matcher.match_requirement(cv, req)
                call_err = (getattr(backend, "last_call", None) or {}).get("error")
                if call_err:  # transport failure (server down, timeout): never record it as a model answer
                    raise SystemExit(f"backend call failed at {c['case_id']}/{req.req_id}: {call_err}; nothing recorded, resume later")
                g = c["gold"][req.req_id]
                ans = parse_model_output(info["raw"])
                quotes = ans.evidence if ans else []
                rec = {"case_id": c["case_id"], "req_id": req.req_id, "tags": g["tags"],
                       "gold_decision": g["decision"], "gold_basis": g["basis"], "gold_evidence": g["evidence"],
                       "gold_spans": [find_span(cv.text, q) for q in g["evidence"]],
                       "decision": res.decision, "basis": res.basis, "model_decision": res.model_decision,
                       "parsed": info["parsed"], "raw": info["raw"], "raw_quotes": quotes,
                       "raw_quotes_valid": sum(find_span(cv.text, q) is not None for q in quotes),
                       "evidence": res.evidence, "evidence_spans": res.evidence_spans,
                       "needs_human_review": res.needs_human_review, "review_reasons": res.review_reasons,
                       "rag_refs": res.rag_refs, "latency_s": round(info["latency_s"], 4),
                       **({"call": backend.last_call} if getattr(backend, "last_call", None) is not None else {})}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
            print(f"{c['case_id']} done", flush=True)

    keys = {(c["case_id"], r["req_id"]) for c in cases for r in c["job"]["requirements"]}
    recs = [r for r in read_jsonl(pred_path) if (r["case_id"], r["req_id"]) in keys]
    m = metrics.compute(recs)
    m["peak_rss_mb"] = round(peak_rss_mb(), 1)
    m["load_seconds"] = cfg["load_seconds"]
    (out / "metrics.json").write_text(json.dumps(m, indent=2) + "\n")
    label = "MOCK " if not cfg["backend"].get("is_model", False) and a.backend.startswith("mock") else ""
    title = f"{label}{a.run_id}: {cfg['backend'].get('model_id') or cfg['backend'].get('backend')}" + \
            (f" + {a.adapter}" if a.adapter else "") + f" | knowledge={knowledge.name} | split={a.split}"
    (out / "metrics.md").write_text(metrics.to_markdown(m, title) +
                                    f"\nPeak RSS: {m['peak_rss_mb']} MB; model load: {cfg['load_seconds']} s\n")
    print(json.dumps({"run_id": a.run_id, "n": m["n"], "macro_f1": round(m["final"]["macro_f1"], 4),
                      "false_met_rate": m["final"]["false_met_rate"], "json_validity": m["json_schema_validity"]}))
    return m


if __name__ == "__main__":
    run(parse_args())
