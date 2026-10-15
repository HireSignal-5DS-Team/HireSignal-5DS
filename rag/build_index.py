"""Precompute and persist document embeddings for a profile (run once, offline; the API then reuses them).

    HF_HOME=<cache> CUDA_VISIBLE_DEVICES= python rag/build_index.py --profile baseline [--prune]

Embeddings are stored in rag/index/ (Qdrant local mode) under a collection named by model + corpus fingerprint, so
a changed corpus or model gets a new collection and an unchanged one is reused. --prune deletes collections that no
profile in profiles.py uses any more. Stop the API first: one process at a time can open rag/index/.
"""
import argparse
import time
from pathlib import Path

from corpus import build_chunks
from profiles import PROFILES
from retrieval import Retriever

INDEX = Path(__file__).parent / "index"

ap = argparse.ArgumentParser()
ap.add_argument("--profile", default="baseline", choices=PROFILES)
ap.add_argument("--prune", action="store_true")
args = ap.parse_args()
p = PROFILES[args.profile]
t = time.perf_counter()
r = Retriever(build_chunks(p["strategy"]), model=p["model"], store_path=INDEX)
print(f"{args.profile}: collection {r.collection} {'reused' if r.index_reused else 'built'} "
      f"({r.qdrant.count(r.collection).count} vectors) in {time.perf_counter() - t:.1f} s")
if args.prune:
    import hashlib
    keep = set()
    for prof in PROFILES.values():
        chunks = build_chunks(prof["strategy"])
        keep.add(f"{prof['model']}-" + hashlib.sha1("".join(c["chunk_id"] + c["text"] for c in chunks).encode()).hexdigest()[:12])
    for c in r.qdrant.get_collections().collections:
        if c.name not in keep:
            r.qdrant.delete_collection(c.name)
            print("pruned", c.name)
r.close()
