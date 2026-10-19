r"""Retrieval benchmark on rag/eval/queries.jsonl (T09 Part C). Choose on dev, report on test.

Grid: chunking A/B x search bm25 / dense / hybrid x embedding (MiniLM, e5-base, bge-small) x reranker (none,
ms-marco-MiniLM-L-6-v2, bge-reranker-base) x graph expansion (off/on). Metrics: hit@1, hit@3, MRR@10, mean query
latency. Choice on dev: MRR@10, then hit@3, then the simpler config. Then the vector-store comparison (numpy vs Qdrant
local vs Chroma persistent) on the chosen dense setup: same rankings?, build time, query latency, disk size.

Usage: .venv\Scripts\python rag\evaluate.py --out eval\results\<date>_rag_retrieval [--device cuda]
"""
import argparse
import itertools
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rag.retrieval import EscoRetriever  # noqa: E402

EMBEDS = ("all-MiniLM-L6-v2", "multilingual-e5-base", "bge-small-en-v1.5")
RERANKERS = (None, "ms-marco-MiniLM-L-6-v2", "bge-reranker-base")
COMPLEXITY = {"bm25": 0, "dense": 1, "hybrid": 2}


def score(retr, queries):
    rows, lat = [], []
    for q in queries:
        t = time.perf_counter()
        ranked = [retr.concepts[i]["uri"] for i, _ in retr.ranking(q["query"], n=10)]
        lat.append(time.perf_counter() - t)
        ranks = [r for r, u in enumerate(ranked, 1) if u in q["gold_uris"]]
        rows.append({"qid": q["qid"], "rank": ranks[0] if ranks else None, "top3": ranked[:3]})
    n = len(rows)
    return {"n": n, "hit@1": round(sum(r["rank"] == 1 for r in rows) / n, 3),
            "hit@3": round(sum(bool(r["rank"]) and r["rank"] <= 3 for r in rows) / n, 3),
            "mrr@10": round(sum(1 / r["rank"] for r in rows if r["rank"]) / n, 3),
            "latency_ms": round(1000 * sum(lat) / n, 2)}, rows


def complexity(cfg):
    return (COMPLEXITY[cfg["search"]], bool(cfg["reranker"]), cfg["graph"], cfg["chunking"] == "B")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--device", default="cuda")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    queries = [json.loads(line) for line in open(ROOT / "rag/eval/queries.jsonl", encoding="utf-8")]
    split = {s: [q for q in queries if q["split"] == s] for s in ("dev", "test")}
    configs = []
    for chunking, reranker, graph in itertools.product("AB", RERANKERS, (False, True)):
        configs.append({"chunking": chunking, "search": "bm25", "embed": None, "reranker": reranker, "graph": graph})
        for search, embed in itertools.product(("dense", "hybrid"), EMBEDS):
            configs.append({"chunking": chunking, "search": search, "embed": embed, "reranker": reranker, "graph": graph})
    results, cache = [], {}
    for cfg in configs:
        key = (cfg["chunking"], cfg["search"], cfg["embed"])
        base = cache.get(key) or EscoRetriever(cfg["chunking"], cfg["search"], cfg["embed"], device=a.device)
        cache[key] = base
        base.rerank_model, base.graph = cfg["reranker"], cfg["graph"]
        res = {s: score(base, qs) for s, qs in split.items()}
        results.append({"config": cfg, "build_s": base.build_s, **{s: res[s][0] for s in res},
                        "per_query": {s: res[s][1] for s in res}})
        print(json.dumps(cfg), {s: {k: res[s][0][k] for k in ("hit@1", "hit@3", "mrr@10", "latency_ms")} for s in res},
              flush=True)
    best = max(results, key=lambda r: (r["dev"]["mrr@10"], r["dev"]["hit@3"], tuple(-x for x in complexity(r["config"]))))
    current = next(r for r in results if r["config"] == {"chunking": "A", "search": "bm25", "embed": None,
                                                        "reranker": None, "graph": False})

    # vector stores on the best dense setup (the chosen one if it uses vectors, else the best dense config)
    dense_best = best if best["config"]["search"] != "bm25" else max(
        (r for r in results if r["config"]["search"] != "bm25"), key=lambda r: (r["dev"]["mrr@10"], r["dev"]["hit@3"]))
    c = dense_best["config"]
    stores = {}
    ref_rank = None
    for store in ("numpy", "qdrant", "chroma"):
        d = out / "stores" / store
        if d.exists():
            shutil.rmtree(d)
        t = time.perf_counter()
        r = EscoRetriever(c["chunking"], c["search"], c["embed"], store=store, reranker=c["reranker"], graph=c["graph"],
                          device=a.device, store_dir=d)
        build = round(time.perf_counter() - t, 2)
        lat, ranks = [], []
        r.ranking("warm-up query", n=10)  # first call loads / compiles: not counted
        for q in queries:
            t = time.perf_counter()
            ranks.append([i for i, _ in r.ranking(q["query"], n=10)])
            lat.append(time.perf_counter() - t)
        ref_rank = ref_rank or ranks
        size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) if d.exists() else int(r.vectors.nbytes)
        stores[store] = {"build_s_incl_embedding": build, "query_latency_ms": round(1000 * sum(lat) / len(lat), 2),
                         "disk_bytes": size, "same_top10_as_numpy": sum(x == y for x, y in zip(ranks, ref_rank)),
                         "queries": len(queries)}
        if store != "numpy":
            r._client = None  # release the local Qdrant / Chroma files
    summary = {"label": f"real-{'GPU' if a.device == 'cuda' else 'CPU'} (embeddings / rerankers on {a.device})",
               "queries": {s: len(qs) for s, qs in split.items()}, "chosen_on_dev": best, "current_v0": current,
               "stores_on": c, "stores": stores, "all": [{k: r[k] for k in ("config", "build_s", "dev", "test")} for r in results]}
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    (out / "per_query.json").write_text(json.dumps([{"config": r["config"], "per_query": r["per_query"]} for r in results]),
                                        encoding="utf-8")
    print("CURRENT", current["config"], current["dev"], current["test"])
    print("CHOSEN", best["config"], best["dev"], best["test"])
    print("STORES", json.dumps(stores))


if __name__ == "__main__":
    main()
