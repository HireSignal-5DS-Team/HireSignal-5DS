"""Known-answer retrieval evaluation: 2 chunking strategies x retrieval modes x embedding models.

Gold evidence is a verbatim quote from the posting, resolved to a character span, so both chunking
strategies are scored against the same answer. A retrieved job chunk is a hit when it is from the gold
posting and covers >= 50% of the gold span's characters. ESCO queries are hits on the gold URI.

Usage:
    python rag/evaluate.py                       # BM25 only (no model download needed)
    python rag/evaluate.py --models e5-small bge-m3
Outputs rag/eval/results/{results.csv, rankings.jsonl, summary.md}.
"""
import argparse
import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd

from chunking import STRATEGIES
from corpus import build_chunks, load_esco, load_jobs
from retrieval import Retriever

HERE = Path(__file__).parent
OUT = HERE / "eval/results"
MIN_COVER = 0.5


def load_queries(jobs, path=HERE / "eval/queries.jsonl"):
    texts = {j["doc_id"]: j["text"] for j in jobs}
    queries = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    for q in queries:
        spans = []
        for quote in q.get("gold_quotes", []):
            body = texts[q["job_id"]]
            # scraped postings repeat some passages; every verbatim occurrence is valid evidence
            found = [(m.start(), m.end()) for m in re.finditer(re.escape(quote), body)]
            if not found:
                raise ValueError(f"{q['qid']}: gold quote not found verbatim in {q['job_id']}: {quote!r}")
            spans += found
        q["spans"] = spans
    return queries


def is_hit(q, chunk):
    if q["type"] == "esco":
        return chunk["doc_id"] in q["gold_uris"]
    if chunk["doc_id"] != q["job_id"]:
        return False
    return any(max(0, min(e, chunk["end"]) - max(s, chunk["start"])) >= MIN_COVER * (e - s) for s, e in q["spans"])


def run(retriever, queries, mode, k=10):
    rows = []
    for q in queries:
        settings = {"job": [("scoped", {"doc_id": q.get("job_id")}), ("global", {"source_type": "job"})],
                    "esco": [("esco", {"source_type": "esco"})],
                    "none": [("none", {"source_type": q.get("collection", "job")})]}[q["type"]]
        for setting, filters in settings:
            t = time.perf_counter()
            out = retriever.search(q["query"], k=k, mode=mode, filters=filters)
            ms = (time.perf_counter() - t) * 1000
            ranks = [i for i, (c, _) in enumerate(out["results"], 1) if q["type"] != "none" and is_hit(q, c)]
            rows.append({"qid": q["qid"], "type": q["type"], "lang": q.get("lang", "en"), "setting": setting,
                         "first_hit_rank": ranks[0] if ranks else None, "status": out["status"],
                         "best_dense_score": out["best_dense_score"], "ms": ms,
                         "top3": [c["chunk_id"] for c, _ in out["results"][:3]]})
    return rows


def calibrate_tau(rows):
    """Pick the abstention threshold on even-numbered queries, report it on odd ones (no test-set tuning)."""
    df = pd.DataFrame([r for r in rows if r["setting"] in ("scoped", "esco", "none") and r["best_dense_score"] is not None])
    if df.empty or not (df.type == "none").any():
        return None, None
    df["answerable"] = df.type != "none"
    dev = df[df.qid.str[-1].astype(int) % 2 == 0]
    grid = np.unique(df.best_dense_score.round(3))
    tau = max(grid, key=lambda t: ((dev.best_dense_score >= t) == dev.answerable).mean())
    test = df[df.qid.str[-1].astype(int) % 2 == 1]
    return float(tau), float(((test.best_dense_score >= tau) == test.answerable).mean())


def summarise(df):
    def agg(g):
        r = g.first_hit_rank
        # one relevant item per query (first gold hit), so Recall@k = Hit@k and nDCG@10 = mean 1/log2(rank+1)
        return pd.Series({"n": len(g), "hit@1": (r == 1).sum(), "hit@5": (r <= 5).sum(), "hit@10": (r <= 10).sum(),
                          "MRR@10": (1 / r).fillna(0).mean().round(3),
                          "nDCG@10": (1 / np.log2(r + 1)).fillna(0).mean().round(3), "ms/query": g.ms.mean().round(1)})
    ans = df[df.type != "none"]
    return ans.groupby(["strategy", "model", "mode", "setting"]).apply(agg, include_groups=False).reset_index()


def no_answer(df):
    none = df[df.type == "none"]
    if none.empty:
        return pd.DataFrame({"note": ["no no-answer queries in this set"]})
    return none.groupby(["strategy", "model", "mode"]).apply(
        lambda g: pd.Series({"n": len(g), "correct_no_match": int((g.status == "no_match").sum())}),
        include_groups=False).reset_index()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=[])
    ap.add_argument("--batch", help="evaluate only queries of this batch, on the postings they reference")
    ap.add_argument("--queries", type=Path, help="alternative query file, e.g. eval/queries_reviewed.jsonl")
    args = ap.parse_args()
    jobs, esco = load_jobs(), load_esco()
    queries = load_queries(jobs, args.queries) if args.queries else load_queries(jobs)
    # results of a reviewed query set go next to, never over, the original results
    out = OUT.parent / f"results_{args.queries.stem}" if args.queries else OUT
    if args.batch:
        queries = [q for q in queries if q.get("batch") == args.batch]
        jobs = [j for j in jobs if j["doc_id"] in {q.get("job_id") for q in queries}]
        out = OUT.parent / f"results_{args.batch}"
    out.mkdir(parents=True, exist_ok=True)
    stats, all_rows, notes = [], [], []
    for strategy in STRATEGIES:
        chunks = build_chunks(strategy, jobs, esco)
        jc = [c for c in chunks if c["source_type"] == "job"]
        mean_words = np.mean([len(c["text"].split()) for c in jc]) if jc else 0
        stats.append(f"| {strategy} | {len(jc)} | {mean_words:.0f} |")
        for model in [None] + args.models:
            # own index folder: Qdrant local mode locks a folder, and the API may hold index/
            r = Retriever(chunks, model=model, store_path=HERE / "index_eval" if model else None)
            modes = ["bm25"] if model is None else ["dense", "hybrid"]
            for mode in modes:
                rows = run(r, queries, mode)
                for row in rows:
                    row.update(strategy=strategy, model=model or "-", mode=mode)
                all_rows += rows
            if model:
                r.qdrant.close()  # Qdrant local mode allows one client per folder
                tau, acc = calibrate_tau(rows)
                notes.append(f"- {strategy} / {model}: tau={tau} (chosen on even qids), "
                             f"answer-vs-abstain accuracy on odd qids={acc}")
    df = pd.DataFrame(all_rows)
    df.drop(columns="top3").to_csv(out / "results.csv", index=False)
    with open(out / "rankings.jsonl", "w") as f:
        for row in all_rows:
            f.write(json.dumps(row, default=str) + "\n")
    table = summarise(df)
    md = (f"# Retrieval evaluation results (generated by evaluate.py)\n\n"
          f"Jobs: {len(jobs)}, ESCO entries: {len(esco)}, queries: {len(queries)} "
          f"({pd.Series([q['type'] for q in queries]).value_counts().to_dict()})\n\n"
          "## Chunk statistics (job postings)\n\n| strategy | chunks | mean words/chunk |\n|---|---|---|\n"
          + "\n".join(stats) + "\n\n## Retrieval (hit counts out of n)\n\n" + table.to_markdown(index=False)
          + "\n\n## No-answer queries (correct = status no_match)\n\n"
          + no_answer(df).to_markdown(index=False)
          + "\n\n## Abstention\n\n" + ("\n".join(notes) or "- not run (needs a dense model)") + "\n")
    (out / "summary.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
