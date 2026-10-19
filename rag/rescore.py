r"""T09b Part B: re-score the retrieval configurations of the RAG_REPORT section-4 table on rag/eval/queries.jsonl
(golds checked by the Approver). Same scoring as rag/evaluate.py; choose on dev (MRR@10, then hit@3, then simpler).

Usage: .venv\Scripts\python rag\rescore.py --out eval\results\<date>_rag_retrieval_checked [--device cuda]
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rag.evaluate import complexity, score  # noqa: E402
from rag.retrieval import EscoRetriever, load_concepts  # noqa: E402

M, E5, BGE = "all-MiniLM-L6-v2", "multilingual-e5-base", "bge-small-en-v1.5"
MS, BR = "ms-marco-MiniLM-L-6-v2", "bge-reranker-base"
CONFIGS = [  # (name, chunking, search, embed, reranker, graph) = the rows of rag/RAG_REPORT.md section 4
    ("BM25 (current V0)", "A", "bm25", None, None, False),
    ("BM25, chunking B", "B", "bm25", None, None, False),
    ("dense all-MiniLM-L6-v2", "A", "dense", M, None, False),
    ("dense multilingual-e5-base", "A", "dense", E5, None, False),
    ("dense bge-small-en-v1.5", "A", "dense", BGE, None, False),
    ("dense MiniLM, chunking B", "B", "dense", M, None, False),
    ("hybrid MiniLM (RRF)", "A", "hybrid", M, None, False),
    ("hybrid bge-small (RRF)", "A", "hybrid", BGE, None, False),
    ("hybrid MiniLM + ms-marco rerank", "A", "hybrid", M, MS, False),
    ("hybrid MiniLM + rerank + graph", "A", "hybrid", M, MS, True),
    ("dense MiniLM + ms-marco rerank", "A", "dense", M, MS, False),
    ("dense MiniLM + bge-reranker-base", "A", "dense", M, BR, False),
    ("dense MiniLM + graph expansion", "A", "dense", M, None, True),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--device", default="cuda")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    queries = [json.loads(line) for line in open(ROOT / "rag/eval/queries.jsonl", encoding="utf-8")]
    labels = [c["label"] for c in load_concepts()]
    dup = sorted({x for q in queries for x in q["gold_labels"] if labels.count(x) > 1})
    split = {s: [q for q in queries if q["split"] == s] for s in ("dev", "test")}
    cache, results = {}, []
    for name, chunking, search, embed, reranker, graph in CONFIGS:
        key = (chunking, search, embed)
        base = cache.get(key) or EscoRetriever(chunking, search, embed, device=a.device)
        cache[key] = base
        base.rerank_model, base.graph = reranker, graph
        res = {s: score(base, qs) for s, qs in split.items()}
        cfg = {"chunking": chunking, "search": search, "embed": embed, "reranker": reranker, "graph": graph}
        results.append({"name": name, "config": cfg, **{s: res[s][0] for s in res}, "per_query": {s: res[s][1] for s in res}})
        print(name, {s: {k: res[s][0][k] for k in ("hit@1", "hit@3", "mrr@10")} for s in res}, flush=True)
    best = max(results, key=lambda r: (r["dev"]["mrr@10"], r["dev"]["hit@3"], tuple(-x for x in complexity(r["config"]))))
    summary = {"label": f"real-{'GPU' if a.device == 'cuda' else 'CPU'}", "golds": "checked by the Approver 2026-10-18",
               "queries": {s: len(qs) for s, qs in split.items()}, "duplicate_gold_labels_in_esco": dup,
               "chosen_on_dev": best["name"], "results": results}
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print("CHOSEN", best["name"], best["dev"], best["test"], "duplicate labels:", dup)


if __name__ == "__main__":
    main()
