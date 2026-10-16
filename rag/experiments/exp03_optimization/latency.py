"""Repeated end-to-end latency (query embedding + exact search + optional reranking) for the finalists.
20 fixed Matcher-setting queries (ESCO + job-filtered) × 5 repeats (3 for configurations slower than 1.5 s),
after a warm-up pass. -> results/latency_summary.csv, results/latency_raw.csv

    python latency.py [cpu|cuda]
"""
import json
import sys
import time

import numpy as np
import pandas as pd

import run as R

device = sys.argv[1] if len(sys.argv) > 1 else "cpu"
if device != "cpu":
    raise SystemExit("GPU latency must be measured on a machine with CUDA; this container has none (reported as blocked)")
jobs, esco = R.load_jobs(), R.load_esco()
qs = [q for q in R.load_queries(jobs, R.SPLITS["dev"]) if q["type"] in ("esco", "job")]
sample = (qs[:10] + [q for q in qs if q["type"] == "job"][:10])[:20]
raw, summ = [], []
for group, spec, emb, rr, n in json.load(open(R.HERE / "finalists.json")):
    jc = [c for j in jobs for c in R.chunk_fn(spec)(j)]
    chunks = jc + [{**e, "chunk_id": e["doc_id"], "section": None, "start": None, "end": None} for e in esco]
    idx = R.exp02.Index(f"dense:{emb}", chunks, {})
    retrieve = R.make_retriever(chunks, idx, rr, n)
    doc = np.array([c["doc_id"] for c in chunks])
    src = np.array([c["source_type"] for c in chunks])
    masks = [(doc == q["job_id"]) if q["type"] == "job" else (src == "esco") for q in sample]
    for q, mk in zip(sample, masks):  # warm-up pass
        retrieve(q["query"], mk)
    cfg = f"{spec} | {emb}" + (f" > {rr}@{n}" if rr else "")
    t0 = time.perf_counter()
    retrieve(sample[0]["query"], masks[0])
    repeats = 3 if (time.perf_counter() - t0) > 1.5 else 5
    per_rep = []
    for rep in range(repeats):
        times = []
        for q, mk in zip(sample, masks):
            t = time.perf_counter()
            retrieve(q["query"], mk)
            times.append((time.perf_counter() - t) * 1000)
            raw.append({"config": cfg, "repeat": rep, "qid": q["qid"], "ms": times[-1]})
        per_rep.append(np.median(times))
    allms = np.array([r["ms"] for r in raw if r["config"] == cfg])
    summ.append({"config": cfg, "device": device, "calls": len(allms), "repeats": repeats,
                 "median ms": round(float(np.median(allms)), 1), "p95 ms": round(float(np.percentile(allms, 95)), 1),
                 "repeat-median min..max ms": f"{min(per_rep):.0f}..{max(per_rep):.0f}"})
    print(summ[-1], flush=True)
    pd.DataFrame(raw).to_csv(R.OUT / "latency_raw.csv", index=False)
    pd.DataFrame(summ).to_csv(R.OUT / "latency_summary.csv", index=False)
