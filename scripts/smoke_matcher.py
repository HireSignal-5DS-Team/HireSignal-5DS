"""LoRA effect smoke test: Matcher prompt v1 on N bench-v1 val requirements, through llama-server.

Arms = adapter scale x knowledge:
  base_k  scale 0 + BM25-ESCO k=3     lora_k  scale 1 + BM25-ESCO k=3   (main comparison: LoRA trained with knowledge)
  base_0  scale 0, no knowledge       lora_0  scale 1, no knowledge     (secondary)
  plain_k no "lora" field at all (use with a server started WITHOUT --lora, to check that scale 0 == plain model)

Usage:
  .venv\\Scripts\\python scripts\\smoke_matcher.py --out eval\\results\\2026-10-18_lora_check --arms base_k,lora_k,base_0,lora_0
  --schema services\\matcher\\schema.json  constrained decoding: response_format json_object + schema (llama-server grammar)
  --n 0                                   all val requirements (full val run)
Writes: config.json, items.json, <arm>.jsonl (per-item outputs), summary.json, summary.md.
"""
import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rag.bm25_esco import BM25EscoKnowledge  # noqa: E402

from services.matcher.prompt import (BASES, CLASSES, DECODING, KEYS, fence_safe, format_knowledge,  # noqa: E402,F401
                                     load_prompt, parse_strict, user_message)

ARMS = {"base_k": (0.0, True), "lora_k": (1.0, True), "base_0": (0.0, False), "lora_0": (1.0, False),
        "plain_k": (None, True), "plain_0": (None, False)}


def select_items(val_path, n, seed):
    cases = [json.loads(line) for line in open(val_path, encoding="utf-8")]
    pool = [(c["case_id"], r["req_id"]) for c in cases for r in c["job"]["requirements"]]
    picked = sorted(random.Random(seed).sample(pool, n)) if n else pool  # n=0: all, in file order
    by_id = {c["case_id"]: c for c in cases}
    items = []
    for cid, rid in picked:
        c = by_id[cid]
        req = next(r for r in c["job"]["requirements"] if r["req_id"] == rid)
        items.append({"case_id": cid, "req_id": rid, "req": req, "cv_text": c["cv"]["text"],
                      "gold": c["gold"][rid]["decision"], "gold_basis": c["gold"][rid]["basis"]})
    return items, len(pool)


def call(client, url, model, messages, scale, schema=None):
    body = {"model": model, "messages": messages, "cache_prompt": False, **DECODING}
    if schema is not None:
        # llama-server b11139 tools/server/README.md:1316: response_format {"type": "json_object", "schema": ...}
        # is compiled to a grammar (same request form V2 used, matcher/backends_api.py:127)
        body["response_format"] = {"type": "json_object", "schema": schema}
    if scale is not None:
        body["lora"] = [{"id": 0, "scale": scale}]
    t = time.perf_counter()
    r = client.post(url, json=body)
    latency = time.perf_counter() - t
    r.raise_for_status()
    d = r.json()
    return d["choices"][0]["message"]["content"], latency, d.get("usage", {}), d.get("timings", {})


def metrics(rows):
    gold = [r["gold"] for r in rows]
    pred = [r["pred"] for r in rows]
    f1s = {}
    for c in CLASSES:
        tp = sum(g == c and p == c for g, p in zip(gold, pred))
        fp = sum(g != c and p == c for g, p in zip(gold, pred))
        fn = sum(g == c and p != c for g, p in zip(gold, pred))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1s[c] = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    quotes = [q for r in rows if r["parsed"] for q in r["parsed"]["evidence"]]
    return {"n": len(rows),
            "valid_json_rate": sum(r["parsed"] is not None for r in rows) / len(rows),
            "accuracy": sum(g == p for g, p in zip(gold, pred)) / len(rows),
            "macro_f1": sum(f1s.values()) / len(CLASSES), "f1_per_class": f1s,
            "false_met": sum(p == "MET" and g != "MET" for g, p in zip(gold, pred)),
            "quotes_total": len(quotes),
            "quotes_verbatim": sum(r["quotes_verbatim"] for r in rows),
            "mean_latency_s": sum(r["latency_s"] for r in rows) / len(rows),
            "pred_counts": {c: pred.count(c) for c in CLASSES},
            "confusion": {g: {p: sum(x == g and y == p for x, y in zip(gold, pred)) for p in CLASSES} for g in CLASSES}}


def main():
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--val", default=str(ROOT / "data/processed/bench-v1/val.jsonl"))
    ap.add_argument("--prompt", default=str(ROOT / "prompts/matcher/v1.md"))
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20261018)
    ap.add_argument("--arms", default="base_k,lora_k,base_0,lora_0")
    ap.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8090/v1"))
    ap.add_argument("--model", default=os.environ.get("LLM_MODEL", "qwen3-4b"))
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--schema", help="JSON schema file for constrained decoding (default: none)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    system, template = load_prompt(a.prompt)
    items, pool = select_items(a.val, a.n, a.seed)
    a.n = len(items)
    schema = json.loads(Path(a.schema).read_text(encoding="utf-8")) if a.schema else None
    kb = BM25EscoKnowledge()
    for it in items:
        it["refs"] = kb.lookup(it["req"], k=a.k)
    (out / "items.json").write_text(json.dumps(
        [{k: it[k] for k in ("case_id", "req_id", "gold", "gold_basis")} | {"requirement": it["req"]["text"],
         "rag_refs": [r["source_id"] for r in it["refs"]]} for it in items], indent=1), encoding="utf-8")

    client = httpx.Client(timeout=300)
    url = a.base_url.rstrip("/") + "/chat/completions"
    props = client.get(a.base_url.rstrip("/").removesuffix("/v1") + "/props").json()
    config = {"date": time.strftime("%Y-%m-%d %H:%M:%S"), "label": "real-GPU", "arms": a.arms.split(","),
              "n": a.n, "pool_size": pool, "seed": a.seed, "val": str(Path(a.val).relative_to(ROOT)),
              "prompt": str(Path(a.prompt).relative_to(ROOT)), "knowledge": {"name": kb.name, "version": kb.version, "k": a.k},
              "decoding": DECODING, "cache_prompt": False,
              "schema": str(Path(a.schema).resolve().relative_to(ROOT)) if a.schema else None, "server_url": a.base_url, "model": a.model,
              "server_props": {k: props.get(k) for k in ("model_path", "build_info", "total_slots")}
              | {"n_ctx": (props.get("default_generation_settings") or {}).get("n_ctx")}}
    (out / "config.json").write_text(json.dumps(config, indent=1), encoding="utf-8")

    summary = {}
    for arm in a.arms.split(","):
        scale, use_k = ARMS[arm]
        call(client, url, a.model, [{"role": "user", "content": "Reply OK."}], scale)  # warm-up, not timed
        rows = []
        with open(out / f"{arm}.jsonl", "w", encoding="utf-8") as f:
            for it in items:
                msgs = [{"role": "system", "content": system},
                        {"role": "user", "content": user_message(template, it["cv_text"], it["req"], it["refs"] if use_k else [])}]
                raw, lat, usage, timings = call(client, url, a.model, msgs, scale, schema)
                parsed = parse_strict(raw)
                pred = parsed["decision"] if parsed else "UNCERTAIN"  # invalid output -> UNCERTAIN (V2 validator rule)
                verb = sum(q in it["cv_text"] for q in parsed["evidence"]) if parsed else 0
                row = {"case_id": it["case_id"], "req_id": it["req_id"], "gold": it["gold"], "pred": pred,
                       "parsed": parsed, "raw": raw, "quotes_verbatim": verb, "latency_s": round(lat, 3),
                       "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens")}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                rows.append(row)
        summary[arm] = metrics(rows)
        m = summary[arm]
        print(f"{arm}: valid {m['valid_json_rate']:.3f} acc {m['accuracy']:.3f} macroF1 {m['macro_f1']:.3f} "
              f"falseMET {m['false_met']} lat {m['mean_latency_s']:.2f}s", flush=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")

    golds = [it["gold"] for it in items]
    lines = [f"# LoRA check — {a.n} bench-v1 val requirements (real-GPU{', SMOKE TEST, not a benchmark' if a.n < pool else ', full val split'})", "",
             f"Gold: " + ", ".join(f"{c} {golds.count(c)}" for c in CLASSES) +
             (f". Seed {a.seed}, sampled from {pool} val requirements." if a.n < pool else f". All {pool} val requirements.") +
             f" Server: {config['server_props'].get('build_info')}.", "",
             "| arm | adapter scale | knowledge | valid JSON | accuracy | macro-F1 | false-MET | verbatim quotes | mean latency (s) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for arm, m in summary.items():
        scale, use_k = ARMS[arm]
        lines.append(f"| {arm} | {'none (no lora field)' if scale is None else scale} | {'BM25-ESCO k=3' if use_k else 'none'} | "
                     f"{m['valid_json_rate']:.3f} | {m['accuracy']:.3f} | {m['macro_f1']:.3f} | {m['false_met']} | "
                     f"{m['quotes_verbatim']}/{m['quotes_total']} | {m['mean_latency_s']:.2f} |")
    lines += ["", f"Constrained decoding: {config['schema'] or 'off'}.", "", "Per-class F1 and confusion matrix (rows = gold, columns = predicted):", ""]
    for arm, m in summary.items():
        lines += [f"**{arm}**: F1 " + ", ".join(f"{c} {m['f1_per_class'][c]:.3f}" for c in CLASSES), "",
                  "| gold / pred | " + " | ".join(CLASSES) + " |", "|---|---|---|---|"]
        lines += [f"| {g} | " + " | ".join(str(m["confusion"][g][p]) for p in CLASSES) + " |" for g in CLASSES] + [""]
    lines += [f"{a.n} items: one item = {100 / a.n:.1f} accuracy points. bench-v1 is SYNTHETIC (V2 generator), not real CVs."]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
