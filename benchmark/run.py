"""Run the Matcher on a benchmark split and score it. Resumable: completed (case_id, req_id) pairs are skipped.

  python benchmark/run.py --split val --backend lexical --knowledge rag --out benchmark/results/val_lexical_rag
  python benchmark/run.py --split val --backend transformers --model Qwen/Qwen3-0.6B --out benchmark/results/val_qwen
  python benchmark/run.py --split test ... --i-am-final-report     # test.jsonl is locked (CONTRACT.md)

mock_oracle replays gold labels through the full pipeline (sanity check of plumbing/metrics, NOT a model result).
"""
import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "4")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmark"))

from matcher import CV, Job, Matcher, Requirement  # noqa: E402
from matcher.prompt import PROMPT_VERSION  # noqa: E402
from matcher.validate import parse_model_output, validate  # noqa: E402
from matcher.backends import LexicalBaseline, MockBackend  # noqa: E402
from matcher.knowledge import FixtureKnowledge, NoKnowledge  # noqa: E402

import metrics as M  # noqa: E402


def load_split(split):
    with open(ROOT / "benchmark/data" / f"{split}.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def fixture_entries():
    from generate_train import SKILLS

    return [{"source_id": f"fixture:{name}", "title": name, "aliases": eqs,
             "text": f"{name}. Also known as: {'; '.join(eqs) or 'n/a'}. Related but different: {', '.join(conf)}."}
            for name, eqs, conf, _ in SKILLS]


def make_knowledge(kind):
    if kind == "rag":
        from matcher.knowledge import RagKnowledge
        return RagKnowledge()
    return FixtureKnowledge(fixture_entries()) if kind == "fixture" else NoKnowledge()


def make_backend(args, cases):
    if args.backend == "lexical":
        return LexicalBaseline()
    if args.backend == "mock_oracle":
        gold = {(c["cv"]["cv_id"], rid): g for c in cases for rid, g in c["gold"].items()}

        def oracle(task):
            g = gold[(task.cv.cv_id, task.req.req_id)]
            return json.dumps({"decision": g["decision"], "basis": g["basis"], "evidence": g["evidence"][:3],
                               "explanation": "gold replay"})
        return MockBackend(oracle, label="gold-oracle")
    import torch
    from matcher.backends import TransformersBackend

    torch.set_num_threads(4)
    kw = {}
    if args.arm:  # pinned model/adapter revisions from models/candidates.json
        arms = json.loads((Path(__file__).parents[1] / "models/candidates.json").read_text())["arms"]
        a = next((a for a in arms if a["name"] == args.arm), None) or sys.exit(f"unknown arm {args.arm}")
        args.model, args.adapter = a["model_id"], args.adapter or a.get("adapter_id")
        kw = {"revision": a.get("revision"), "chat_kwargs": a.get("chat_kwargs") or None,
              "adapter_revision": a.get("adapter_revision") if args.adapter == a.get("adapter_id") else None}
    if not args.model:
        sys.exit("--model or --arm is required for --backend transformers")
    return TransformersBackend(args.model, adapter_id=args.adapter, max_new_tokens=args.max_new_tokens, **kw)


def load_preds(path):
    """{(case_id, req_id): record}. Drops a torn last line (crash mid-write) and duplicates (last wins), then
    rewrites the file cleanly so appends never join a partial line."""
    if not path.exists():
        return {}
    recs = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            x = json.loads(line)
            recs[(x["case_id"], x["req_id"])] = x
        except (json.JSONDecodeError, KeyError, TypeError):
            print(f"  dropping unreadable line in {path}", flush=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in recs.values()), encoding="utf-8")
    tmp.replace(path)
    return recs


def peak_rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Linux: KiB


def fmt(x, pct=False):
    if x is None:
        return "n/a"
    return f"{x:.1%}" if pct else (f"{x:.3f}" if isinstance(x, float) else str(x))


def summary_md(meta, m):
    f, r = m["final"], m["raw_model"]
    lines = [f"# Benchmark run: {meta['name']}", "",
             f"split `{meta['split']}` · backend `{meta['backend']['backend']}` · knowledge `{meta['knowledge']}` · "
             f"n = {m['n']} requirements", "",
             "| metric | final (after validation) | raw model |", "|---|---|---|",
             f"| accuracy | {fmt(f['accuracy'])} | {fmt(r['accuracy'])} |",
             f"| macro-F1 | {fmt(f['macro_f1'])} | {fmt(r['macro_f1'])} |",
             f"| false-MET rate | {fmt(f['false_met_rate'], True)} | {fmt(r['false_met_rate'], True)} |",
             f"| UNCERTAIN recall | {fmt(f['uncertain_recall'])} | {fmt(r['uncertain_recall'])} |",
             f"| predicted UNCERTAIN share | {fmt(f['predicted_uncertain_share'], True)} | "
             f"{fmt(r['predicted_uncertain_share'], True)} |",
             f"| unsupported MET | {f['unsupported_met']} | |",
             f"| JSON validity | | {fmt(r['json_validity'], True)} |",
             f"| quote verbatim rate | | {fmt(r['quote_verbatim_rate'], True)} ({r['quotes_emitted']} quotes) |",
             "", f"Evidence overlap on gold MET: {fmt(m['evidence_overlap_gold_met'], True)} · "
             f"basis accuracy on MISSING/MISSING: {fmt(m['missing_basis_accuracy'], True)}",
             f"Latency: {m['latency']['mean_s']:.3f} s/req (max {m['latency']['max_s']:.2f} s) · "
             f"peak RSS {meta['peak_rss_mb']:.0f} MB (last process)", "",
             "## Confusion (rows gold, columns final prediction)", "", "| gold \\ pred | MET | MISSING | UNCERTAIN |",
             "|---|---|---|---|"]
    lines += [f"| {g} | " + " | ".join(str(f["confusion"][g].get(p, 0)) for p in M.CLASSES) + " |" for g in M.CLASSES]
    lines += ["", "## Per class (final)", "", "| class | precision | recall | F1 | support |", "|---|---|---|---|---|"]
    lines += [f"| {c} | {fmt(v['precision'])} | {fmt(v['recall'])} | {fmt(v['f1'])} | {v['support']} |"
              for c, v in f["per_class"].items()]
    lines += ["", "## Per tag accuracy (final)", "", "| tag | n | accuracy |", "|---|---|---|"]
    lines += [f"| {t} | {v['n']} | {fmt(v['accuracy'])} |" for t, v in m["per_tag"].items()]
    if meta["backend"].get("is_model") is False:
        lines += ["", f"Note: backend `{meta['backend']['backend']}` is not a neural model."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=["val", "test"], required=True)
    ap.add_argument("--i-am-final-report", action="store_true", help="required to touch the locked test split")
    ap.add_argument("--backend", choices=["lexical", "mock_oracle", "transformers"], required=True)
    ap.add_argument("--model")
    ap.add_argument("--arm", help="arm name from models/candidates.json (pins revisions)")
    ap.add_argument("--adapter")
    ap.add_argument("--knowledge", choices=["rag", "none", "fixture"], default="rag")
    ap.add_argument("--k", type=int, default=3, help="knowledge entries per requirement")
    ap.add_argument("--limit", type=int, help="score only the first N requirements of the split")
    ap.add_argument("--max-new-tokens", type=int, default=192)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.split == "test" and not args.i_am_final_report:
        sys.exit("test.jsonl is locked; pass --i-am-final-report only for the final report")

    cases = load_split(args.split)
    items = [(c, r) for c in cases for r in c["job"]["requirements"]][:args.limit]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pred_path = out / "predictions.jsonl"
    done = {k for k in load_preds(pred_path)}
    todo = [(c, r) for c, r in items if (c["case_id"], r["req_id"]) not in done]
    print(f"{len(items)} requirements, {len(items) - len(todo)} already done, {len(todo)} to run", flush=True)

    knowledge = make_knowledge(args.knowledge)
    backend = make_backend(args, cases) if todo else None  # nothing to run: do not load a model
    matcher = Matcher(backend, knowledge, k=args.k)
    t_start = time.perf_counter()
    with open(pred_path, "a", encoding="utf-8") as f:
        for i, (c, r) in enumerate(todo, 1):
            cv, job = CV.model_validate(c["cv"]), Job.model_validate(c["job"])
            req = next(x for x in job.requirements if x.req_id == r["req_id"])
            result, info = matcher.match_requirement(cv, req)
            rec = {"case_id": c["case_id"], "req_id": req.req_id, "gold": c["gold"][req.req_id],
                   "result": result.model_dump(), "raw": info["raw"], "parsed": info["parsed"],
                   "latency_s": round(info["latency_s"], 4), "prompt_version": PROMPT_VERSION}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            if i % 10 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} ({time.perf_counter() - t_start:.0f}s)", flush=True)

    keys = {(c["case_id"], r["req_id"]) for c, r in items}
    recs = [x for k, x in load_preds(pred_path).items() if k in keys]
    versions = {x.get("prompt_version", PROMPT_VERSION) for x in recs}
    if versions != {PROMPT_VERSION}:
        sys.exit(f"{pred_path} mixes prompt versions {versions}; rerun into a new --out")
    # re-validate stored raw outputs with the current validator, so rule changes never need a model rerun
    by_key = {(c["case_id"], r["req_id"]): (c, r) for c, r in items}
    for x in recs:
        c, r = by_key[(x["case_id"], x["req_id"])]
        cv, req = CV.model_validate(c["cv"]), Requirement.model_validate(r)
        x["gold"] = c["gold"][r["req_id"]]  # labels may be corrected after a run
        x["result"] = validate(parse_model_output(x["raw"]), cv, req, knowledge.lookup(req, k=args.k)).model_dump()
    m = M.compute(recs, {c["case_id"]: c["cv"]["text"] for c in cases})
    prev = out / "metrics.json"
    info = backend.info() if backend else (json.loads(prev.read_text())["meta"]["backend"] if prev.exists()
                                            else {"backend": args.backend})
    meta = {"name": out.name, "split": args.split, "backend": info,
            "knowledge": knowledge.name, "k": args.k, "limit": args.limit, "model": args.model,
            "adapter": args.adapter, "max_new_tokens": args.max_new_tokens, "peak_rss_mb": round(peak_rss_mb(), 1),
            "torch_threads": 4, "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (out / "metrics.json").write_text(json.dumps({"meta": meta, "metrics": m}, indent=2) + "\n", encoding="utf-8")
    (out / "summary.md").write_text(summary_md(meta, m), encoding="utf-8")
    f_ = m["final"]
    print(f"acc={fmt(f_['accuracy'])} macroF1={fmt(f_['macro_f1'])} falseMET={fmt(f_['false_met_rate'])} -> {out}")
    return m


if __name__ == "__main__":
    main()
