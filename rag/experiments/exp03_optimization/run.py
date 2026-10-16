"""Experiment 03 runner (quality). Latency is measured separately by latency.py with repeats.

    python run.py dev            # all exp03 configurations on the dev set -> results/dev_per_query.csv
    python run.py calibration    # finalists (finalists.json) on the calibration split -> results/calibration_scores.csv
"""
import json
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd
import torch

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent / "exp02_benchmark"))
import importlib.util  # noqa: E402

import chunking  # noqa: E402

# exp02's runner is also called run.py: load it under its own name (Index, encode, DENSE, rss_mb)
_spec = importlib.util.spec_from_file_location("exp02_run", HERE.parent / "exp02_benchmark/run.py")
exp02 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(exp02)
from chunkers import _chunk, sentences, structure_chunks  # noqa: E402
from corpus import load_esco, load_jobs  # noqa: E402
from evaluate import is_hit, load_queries  # noqa: E402

OUT = HERE / "results"
SPLITS = {"dev": HERE.parents[1] / "eval/queries_reviewed.jsonl", "calibration": HERE / "calibration_queries.jsonl"}
RERANKERS = {"mmarco": "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",  # multilingual, 118M
             "msmarco-l6": "cross-encoder/ms-marco-MiniLM-L-6-v2",     # English, 22M
             "bge": "BAAI/bge-reranker-v2-m3"}                         # multilingual, 568M
K = 10


@contextmanager
def params(**kw):
    """Temporarily override the production chunking module's size constants (restored afterwards)."""
    old = {k: getattr(chunking, k) for k in kw}
    for k, v in kw.items():
        setattr(chunking, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(chunking, k, v)


def parent_child_window(job, size=3, stride=2):
    """Children = windows of `size` sentences moved by `stride` (overlap size-stride), inside structure parents."""
    out = []
    for p in structure_chunks(job):
        head = p["text"].split("\n", 1)[0]
        sents = sentences(job["text"], p["start"], p["end"])
        for i in range(0, max(len(sents) - size + stride, 1), stride):
            w = sents[i:i + size]
            s, e = w[0][0], w[-1][1]
            out.append(_chunk(job, "childw", len(out), s, e, f"{head}\n{job['text'][s:e]}", section=p["section"],
                              parent_id=p["chunk_id"], parent_start=p["start"], parent_end=p["end"], parent_text=p["text"]))
    return out


def chunk_fn(spec):
    """'structure@300', 'sliding@200/30', 'pc@1s', 'pc@3s2'."""
    kind, arg = spec.split("@")
    if kind == "structure":
        return lambda j: _with(lambda: structure_chunks(j), MAX_SECTION_WORDS=int(arg))
    if kind == "sliding":
        w, o = map(int, arg.split("/"))
        return lambda j: _with(lambda: chunking.fixed_chunks(j), FIXED_WORDS=w, FIXED_OVERLAP=o)
    if spec == "pc@1s":
        from chunkers import parent_child_chunks
        return parent_child_chunks
    size, stride = map(int, re.fullmatch(r"(\d)s(\d)", arg).groups())
    return lambda j: parent_child_window(j, size, stride)


def _with(fn, **kw):
    with params(**kw):
        return fn()


_rr = {}


def reranker(name):
    if name not in _rr:
        from sentence_transformers import CrossEncoder
        base = name.removesuffix("-int8")
        before, t = exp02.rss_mb(), time.perf_counter()
        ce = CrossEncoder(RERANKERS[base], device="cpu", max_length=512)
        if name.endswith("-int8"):  # dynamic int8 quantisation of Linear layers (CPU only)
            torch.quantization.quantize_dynamic(ce, {torch.nn.Linear}, dtype=torch.qint8, inplace=True)
        _rr[name] = (ce, exp02.rss_mb() - before, time.perf_counter() - t)
    return _rr[name][0]


def units(chunks, order, scores, depth=50):
    """Ranked result units with their first-stage score; parent-child children collapse into their parent."""
    out, seen = [], set()
    for i in order:
        c = chunks[i]
        if "parent_id" in c:
            if c["parent_id"] in seen:
                continue
            seen.add(c["parent_id"])
            c = {**c, "chunk_id": c["parent_id"], "start": c["parent_start"], "end": c["parent_end"], "text": c["parent_text"]}
        out.append((c, float(scores[i])))
        if len(out) == depth:
            break
    return out


def make_retriever(chunks, idx, rr=None, top_n=None):
    def retrieve(query, mask):
        s = np.where(mask, idx.scores(query), -np.inf)
        order = [int(i) for i in np.argsort(-s)[:400] if np.isfinite(s[i])]
        u = units(chunks, order, s)
        top_dense = u[0][1] if u else None
        top_rr = None
        if rr and u:
            head = u[:top_n]
            r = reranker(rr).predict([(query, c["text"]) for c, _ in head], batch_size=16)
            o = np.argsort(-r)
            top_rr = float(r[o[0]])
            u = [head[i] for i in o] + u[top_n:]
        return [c for c, _ in u[:K]], top_dense, top_rr
    return retrieve


SETTINGS = {"dev": {"job": ["scoped", "global"], "esco": ["esco"], "none": ["none"]},
            "calibration": {"job": ["scoped"], "esco": ["esco"], "none": ["none"]}}


def evaluate(cfg, queries, chunks, retrieve, split):
    doc = np.array([c["doc_id"] for c in chunks])
    src = np.array([c["source_type"] for c in chunks])
    rows = []
    retrieve(queries[0]["query"], src == "esco")  # warm-up
    for q in queries:
        for setting in SETTINGS[split][q["type"]]:
            if setting == "scoped" or (setting == "none" and q.get("collection") == "job"):
                mask = doc == q["job_id"]  # job-specific retrieval is always filtered by job ID
            else:
                mask = src == ("job" if setting == "global" else "esco")
            t = time.perf_counter()
            res, top_dense, top_rr = retrieve(q["query"], mask)
            ms = (time.perf_counter() - t) * 1000
            ranks = [r for r, c in enumerate(res, 1) if q["type"] != "none" and is_hit(q, c)]
            rows.append({**cfg, "qid": q["qid"], "type": q["type"], "collection": q.get("collection"), "lang": q.get("lang", "en"),
                         "setting": setting, "rank": ranks[0] if ranks else None, "ms": ms, "top_dense": top_dense,
                         "top_rerank": top_rr, "top_doc": res[0]["doc_id"] if res else None,
                         "top_span": [res[0]["start"], res[0]["end"]] if res else None})
    return rows


def dev_configs():
    """(group, chunker spec, embedding, reranker, top_n)."""
    for spec in ("structure@150", "structure@300", "structure@500", "sliding@100/15", "sliding@200/30",
                 "sliding@300/45", "pc@1s", "pc@3s2"):
        yield "A-chunk-tuning", spec, "e5-small", None, None
    for spec in ("structure@300", "pc@1s"):
        yield "B-embedding", spec, "e5-base", None, None
    for rr in ("msmarco-l6", "mmarco", "bge"):
        for n in (5, 10, 20):
            yield "C-rerank", "structure@300", "e5-small", rr, n
    for rr in ("mmarco-int8", "bge-int8"):
        yield "C-rerank-int8", "structure@300", "e5-small", rr, 10
    for spec, emb in (("pc@1s", "e5-small"), ("pc@1s", "e5-base"), ("structure@300", "e5-base")):
        for rr in ("mmarco", "bge"):
            yield "D-combination", spec, emb, rr, 10


def main(split):
    jobs, esco = load_jobs(), load_esco()
    queries = load_queries(jobs, SPLITS[split])
    cfgs = list(dev_configs()) if split == "dev" else [tuple(c) for c in json.load(open(HERE / "finalists.json"))]
    OUT.mkdir(exist_ok=True)
    rows, meta, chunk_cache, idx_cache, esco_cache = [], [], {}, {}, {}
    for group, spec, emb, rr, n in cfgs:
        if spec not in chunk_cache:
            t = time.perf_counter()
            jc = [c for j in jobs for c in chunk_fn(spec)(j)]
            chunk_cache[spec] = (jc + [{**e, "chunk_id": e["doc_id"], "section": None, "start": None, "end": None} for e in esco],
                                 time.perf_counter() - t)
        chunks, chunk_s = chunk_cache[spec]
        if (spec, emb) not in idx_cache:
            idx_cache[(spec, emb)] = exp02.Index(f"dense:{emb}", chunks, esco_cache)
        idx = idx_cache[(spec, emb)]
        name = f"{spec} | {emb}" + (f" > {rr}@{n}" if rr else "")
        print(f"[{split}] {group:14s} {name}", flush=True)
        cfg = {"group": group, "config": name, "chunker": spec, "embedding": emb, "reranker": rr, "top_n": n}
        rows += evaluate(cfg, queries, chunks, make_retriever(chunks, idx, rr, n), split)
        meta.append({**cfg, "job_chunks": sum(c["source_type"] == "job" for c in chunks), "chunking_s": round(chunk_s, 2),
                     "indexing_s": round(idx.index_s, 1), "index_mb": round(idx.size / 2**20, 2),
                     "embed_mem_mb": round(exp02._models[emb][1]), "rerank_mem_mb": round(_rr[rr][1]) if rr else 0})
        pd.DataFrame(rows).to_csv(OUT / f"{split}_per_query.csv", index=False)  # saved after every config
        pd.DataFrame(meta).to_csv(OUT / f"{split}_configs.csv", index=False)


if __name__ == "__main__":
    main(sys.argv[1])
