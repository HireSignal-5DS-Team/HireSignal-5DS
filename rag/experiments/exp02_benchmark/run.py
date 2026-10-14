"""Experiment 02 runner. Same machine, same procedure for every configuration.

    python run.py dev        # all configurations on the 42-query dev set -> results/dev_*
    python run.py holdout    # only configurations listed in selection.json -> results/holdout_*

Search is exact (numpy) for every dense model, so latency differences come from the encoder, not the index.
Latency = wall time per query (encode + score + optional rerank), after one warm-up query.
"""
import json
import sys
import time
from pathlib import Path

import bm25s
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))
from chunkers import CHUNKERS, NEEDS_ENCODER, coverage  # noqa: E402
from corpus import load_esco, load_jobs  # noqa: E402
from evaluate import is_hit, load_queries  # noqa: E402

OUT = HERE / "results"
DEV = HERE.parents[1] / "eval/queries_reviewed.jsonl"
HOLDOUT = HERE / "holdout_queries.jsonl"
K, CAND, RRF_K = 10, 20, 60
# name -> (Hugging Face id, query prefix, passage prefix); categories: embeddings only
DENSE = {"e5-small": ("intfloat/multilingual-e5-small", "query: ", "passage: "),
         "minilm": ("sentence-transformers/all-MiniLM-L6-v2", "", ""),
         "e5-base": ("intfloat/multilingual-e5-base", "query: ", "passage: "),
         "bge-m3": ("BAAI/bge-m3", "", "")}
RERANKER = "BAAI/bge-reranker-v2-m3"


def rss_mb():
    return int(next(l for l in open("/proc/self/status") if l.startswith("VmRSS")).split()[1]) / 1024


_models = {}


def model(name):
    if name not in _models:
        from sentence_transformers import SentenceTransformer
        before, t = rss_mb(), time.perf_counter()
        m = SentenceTransformer(DENSE[name][0], device="cpu")
        _models[name] = (m, rss_mb() - before, time.perf_counter() - t)
    return _models[name][0]


def encode(name, texts, query=False):
    hf, qp, pp = DENSE[name]
    return model(name).encode([(qp if query else pp) + t for t in texts], normalize_embeddings=True,
                              batch_size=32, convert_to_numpy=True)


class Index:
    """One retriever over job chunks (of one chunker) + ESCO entries. kind: bm25 | tfidf | dense:<model>."""

    def __init__(self, kind, chunks, esco_cache):
        self.kind, self.chunks = kind, chunks
        self.doc = np.array([c["doc_id"] for c in chunks])
        self.src = np.array([c["source_type"] for c in chunks])
        texts = [c["text"] for c in chunks]
        t = time.perf_counter()
        if kind == "bm25":
            self.m = bm25s.BM25()
            self.m.index(bm25s.tokenize(texts, stopwords="en", show_progress=False), show_progress=False)
            self.size = sum(a.nbytes for a in self.m.scores.values() if hasattr(a, "nbytes"))
        elif kind == "tfidf":
            self.m = TfidfVectorizer(stop_words="english", sublinear_tf=True)
            self.X = self.m.fit_transform(texts)
            self.size = self.X.data.nbytes + self.X.indices.nbytes + self.X.indptr.nbytes
        else:
            name = kind.split(":")[1]
            n_job = sum(s == "job" for s in self.src)  # job chunks first, ESCO last (corpus order)
            if name not in esco_cache:  # ESCO vectors are identical for every chunker: encode once, charge every index
                te = time.perf_counter()
                esco_cache[name] = (encode(name, texts[n_job:]), time.perf_counter() - te)
            t = time.perf_counter()
            self.E = np.vstack([encode(name, texts[:n_job]), esco_cache[name][0]])
            self.size = self.E.nbytes
            t -= esco_cache[name][1]
        self.index_s = time.perf_counter() - t

    def scores(self, query):
        if self.kind == "bm25":
            tok = bm25s.tokenize(query, stopwords="en", show_progress=False, return_ids=False)[0]
            return self.m.get_scores(tok) if tok else np.zeros(len(self.chunks))
        if self.kind == "tfidf":
            return (self.X @ self.m.transform([query]).T).toarray().ravel()
        return self.E @ encode(self.kind.split(":")[1], [query], query=True)[0]

    def ranking(self, query, mask):
        depth = 200 if "parent_id" in self.chunks[0] else 50  # parent-child: many children per returned parent
        s = np.where(mask, self.scores(query), -np.inf)
        order = np.argsort(-s)[:depth]
        return [int(i) for i in order if np.isfinite(s[i]) and (self.kind.startswith("dense") or s[i] > 0)]


def rrf(*rankings):
    f = {}
    for r in rankings:
        for rank, i in enumerate(r, 1):
            f[i] = f.get(i, 0) + 1 / (RRF_K + rank)
    return sorted(f, key=lambda i: -f[i])


_ce = None


def rerank(query, chunks, cand):
    global _ce
    if _ce is None:
        from sentence_transformers import CrossEncoder
        before, t = rss_mb(), time.perf_counter()
        _ce = (CrossEncoder(RERANKER, device="cpu", max_length=512), rss_mb() - before, time.perf_counter() - t)
    top = cand[:CAND]
    s = _ce[0].predict([(query, chunks[i].get("parent_text", chunks[i]["text"])) for i in top], batch_size=8)
    return [top[i] for i in np.argsort(-s)] + cand[CAND:]


def results_for(config, chunks, ranked):
    """Map ranked chunk ids to result chunks; parent-child returns parents (deduplicated)."""
    out, seen = [], set()
    for i in ranked:
        c = chunks[i]
        if "parent_id" in c:
            if c["parent_id"] in seen:
                continue
            seen.add(c["parent_id"])
            c = {**c, "chunk_id": c["parent_id"], "start": c["parent_start"], "end": c["parent_end"]}
        out.append(c)
        if len(out) == K:
            break
    return out


SETTINGS = {"job": [("scoped", lambda q: {"doc": q["job_id"]}), ("global", lambda q: {"src": "job"})],
            "esco": [("esco", lambda q: {"src": "esco"})], "none": [("none", lambda q: {"src": q.get("collection", "esco")})]}


def evaluate_config(config, queries, chunks, retrieve):
    doc = np.array([c["doc_id"] for c in chunks])
    src = np.array([c["source_type"] for c in chunks])
    rows, warm = [], False
    for q in queries:
        for setting, filt in SETTINGS[q["type"]]:
            f = filt(q)
            mask = (doc == f["doc"]) if "doc" in f else (src == f["src"])
            if not warm:
                retrieve(q["query"], mask)
                warm = True
            t = time.perf_counter()
            res = results_for(config, chunks, retrieve(q["query"], mask))
            ms = (time.perf_counter() - t) * 1000
            ranks = [r for r, c in enumerate(res, 1) if q["type"] != "none" and is_hit(q, c)]
            rows.append({**config, "qid": q["qid"], "type": q["type"], "lang": q.get("lang", "en"), "setting": setting,
                         "rank": ranks[0] if ranks else None, "returned": len(res), "ms": ms})
    return rows


def build_chunks(chunker, jobs, esco):
    t = time.perf_counter()
    enc = (lambda texts: encode("e5-small", texts)) if chunker in NEEDS_ENCODER else None
    job_chunks = [c for j in jobs for c in (CHUNKERS[chunker](j, enc) if enc else CHUNKERS[chunker](j))]
    chunk_s = time.perf_counter() - t
    cov = min(coverage(j, [c for c in job_chunks if c["doc_id"] == j["doc_id"]]) for j in jobs)
    esco_chunks = [{**e, "chunk_id": e["doc_id"], "section": None, "start": None, "end": None} for e in esco]
    return job_chunks + esco_chunks, chunk_s, cov


def configs():
    """(phase, chunker, first-stage retrievers, fusion, rerank). One variable changes at a time vs the baseline."""
    yield "baseline", "structure", ["dense:e5-small"], None, False
    for ch in CHUNKERS:
        for r in ("dense:e5-small", "bm25"):
            yield "1-chunking", ch, [r], None, False
    yield "2a-lexical", "structure", ["tfidf"], None, False
    for m in DENSE:
        yield "2b-embedding", "structure", [f"dense:{m}"], None, False
    yield "2c-fusion", "structure", ["bm25", "dense:e5-small"], "rrf", False
    yield "2c-fusion", "structure", ["bm25", "dense:bge-m3"], "rrf", False
    yield "2d-rerank", "structure", ["dense:e5-small"], None, True


def run(split):
    jobs, esco = load_jobs(), load_esco()
    queries = load_queries(jobs, DEV if split == "dev" else HOLDOUT)
    allowed = None
    if split == "holdout":
        allowed = {json.dumps(c) for c in json.load(open(HERE / "selection.json"))["evaluate_on_holdout"]}
    OUT.mkdir(exist_ok=True)
    rows, meta, esco_cache, chunk_cache, idx_cache = [], [], {}, {}, {}
    seen = set()
    for phase, chunker, retrievers, fusion, rr in configs():
        key = json.dumps([chunker, retrievers, fusion, rr])
        if key in seen or (allowed is not None and key not in allowed):
            continue
        seen.add(key)
        if chunker not in chunk_cache:
            chunk_cache[chunker] = build_chunks(chunker, jobs, esco)
        chunks, chunk_s, cov = chunk_cache[chunker]
        idx = []
        for r in retrievers:
            if (chunker, r) not in idx_cache:
                idx_cache[(chunker, r)] = Index(r, chunks, esco_cache)
            idx.append(idx_cache[(chunker, r)])

        def retrieve(query, mask, idx=idx, fusion=fusion, rr=rr):
            ranked = rrf(*[i.ranking(query, mask) for i in idx]) if fusion else idx[0].ranking(query, mask)
            return rerank(query, chunks, ranked) if rr else ranked

        name = "+".join(retrievers) + (" RRF" if fusion else "") + (" > rerank" if rr else "")
        config = {"phase": phase, "chunker": chunker, "retriever": name}
        print(f"[{split}] {phase:12s} {chunker:12s} {name}", flush=True)
        rows += evaluate_config(config, queries, chunks, retrieve)
        mem = sum(_models[i.kind.split(':')[1]][1] for i in idx if i.kind.startswith("dense"))
        mem += _ce[1] if rr and _ce else 0
        meta.append({**config, "job_chunks": sum(c["source_type"] == "job" for c in chunks), "coverage": cov,
                     "chunking_s": round(chunk_s, 2), "indexing_s": round(sum(i.index_s for i in idx), 1),
                     "index_mb": round(sum(i.size for i in idx) / 2**20, 2), "model_mem_mb": round(mem)})
    pd.DataFrame(rows).to_csv(OUT / f"{split}_per_query.csv", index=False)
    pd.DataFrame(meta).to_csv(OUT / f"{split}_configs.csv", index=False)


if __name__ == "__main__":
    run(sys.argv[1])
