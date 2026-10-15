"""RAG adapter validation on the benchmark requirements whose skill is an ESCO concept (alias / near-miss items):
does BM25 retrieval of the requirement's skill term return that ESCO concept, and its alias, in the top k?

  python -m benchmark.rag_check --split val
"""
import argparse
import json
from collections import defaultdict

from matcher.knowledge import RagKnowledge
from matcher.schemas import Requirement

from .run import DATA, read_jsonl

TAGS = ("equivalent_skill_alias", "rag_suggests_absent_skill")


def check(split, k=3, use_text=False):
    rag = RagKnowledge()
    by_title = {c["title"].casefold(): c["doc_id"] for c in rag.retriever.chunks}
    stats = defaultdict(lambda: {"n": 0, "hit1": 0, "hitk": 0})
    for c in read_jsonl(DATA / f"{split}.jsonl"):
        for r in c["job"]["requirements"]:
            tags = c["gold"][r["req_id"]]["tags"]
            tag = next((t for t in TAGS if t in tags), None)
            if not tag:
                continue
            uri = by_title[r["skill_terms"][0].casefold()]
            q = {**r, "skill_terms": []} if use_text else r  # use_text: query with the whole requirement sentence
            ids = [x.source_id for x in rag.lookup(Requirement(**q), k=k)]
            s = stats[tag]
            s["n"] += 1
            s["hit1"] += ids[:1] == [uri]
            s["hitk"] += uri in ids
    return {t: {**s, "hit@1": round(s["hit1"] / s["n"], 3), f"hit@{k}": round(s["hitk"] / s["n"], 3)} for t, s in stats.items()}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="val")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--use-text", action="store_true", help="query with the requirement sentence, not the skill term")
    a = ap.parse_args()
    print(json.dumps(check(a.split, a.k, a.use_text), indent=2))
