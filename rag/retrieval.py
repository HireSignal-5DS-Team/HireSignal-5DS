"""BM25, dense and hybrid (RRF) retrieval over job-description chunks and ESCO entries.

- BM25 (bm25s): keyword scoring, strong on exact tool names, needs no model download.
- Dense: sentence-transformers embeddings stored in Qdrant local mode (on-disk, payload filters).
- Hybrid: Reciprocal Rank Fusion, score = sum over retrievers of 1 / (RRF_K + rank).
  RRF scores depend on ranks only, so they are NOT used for abstention.
- Abstention: status "no_match" when the best dense cosine similarity (after filters) is below the
  model's threshold `tau`. Cosine similarity is a text-relevance value, not a probability.
"""
import hashlib

import bm25s
import numpy as np

RRF_K = 60       # standard constant from Cormack et al. (2009)
CANDIDATES = 50  # depth of each ranked list fused by RRF

# name -> (Hugging Face id, query prefix, passage prefix, abstention threshold or None if not calibrated)
MODELS = {
    "e5-small": ("intfloat/multilingual-e5-small", "query: ", "passage: ", None),
    "bge-m3": ("BAAI/bge-m3", "", "", None),
}


class Retriever:
    def __init__(self, chunks, model=None, store_path=None, tau=None):
        self.chunks = chunks
        self.bm25 = bm25s.BM25()
        self.bm25.index(bm25s.tokenize([c["text"] for c in chunks], stopwords="en", show_progress=False),
                        show_progress=False)
        self.model = None
        if model:
            self._init_dense(model, store_path)
            self.tau = tau if tau is not None else MODELS[model][3]

    def _init_dense(self, model, store_path):
        from qdrant_client import QdrantClient, models
        from sentence_transformers import SentenceTransformer

        hf_id, self.q_prefix, p_prefix, _ = MODELS[model]
        self.model = SentenceTransformer(hf_id)
        self.qdrant = QdrantClient(path=str(store_path)) if store_path else QdrantClient(":memory:")
        # collection name fingerprints model + chunk texts, so a changed corpus is re-embedded
        digest = hashlib.sha1("".join(c["chunk_id"] + c["text"] for c in self.chunks).encode()).hexdigest()[:12]
        self.collection = f"{model}-{digest}"
        if not self.qdrant.collection_exists(self.collection):
            vecs = self.model.encode([p_prefix + c["text"] for c in self.chunks], normalize_embeddings=True,
                                     batch_size=32, show_progress_bar=True)
            self.qdrant.create_collection(self.collection, vectors_config=models.VectorParams(
                size=vecs.shape[1], distance=models.Distance.COSINE))
            self.qdrant.upload_collection(self.collection, vectors=vecs, ids=range(len(self.chunks)),
                                          payload=[{"doc_id": c["doc_id"], "source_type": c["source_type"]}
                                                   for c in self.chunks])

    def _mask(self, filters):
        ok = np.ones(len(self.chunks), bool)
        for key, val in (filters or {}).items():
            ok &= np.array([c.get(key) == val for c in self.chunks])
        return ok

    def bm25_ranking(self, query, filters=None, k=CANDIDATES):
        tokens = bm25s.tokenize(query, stopwords="en", show_progress=False, return_ids=False)[0]
        scores = self.bm25.get_scores(tokens) if tokens else np.zeros(len(self.chunks))
        scores = np.where(self._mask(filters), scores, -np.inf)
        order = np.argsort(-scores)[:k]
        return [(int(i), float(scores[i])) for i in order if np.isfinite(scores[i]) and scores[i] > 0]

    def dense_ranking(self, query, filters=None, k=CANDIDATES):
        from qdrant_client import models

        conds = [models.FieldCondition(key=key, match=models.MatchValue(value=val))
                 for key, val in (filters or {}).items()]
        qv = self.model.encode(self.q_prefix + query, normalize_embeddings=True)
        hits = self.qdrant.query_points(self.collection, query=qv.tolist(), limit=k,
                                        query_filter=models.Filter(must=conds) if conds else None).points
        return [(int(h.id), float(h.score)) for h in hits]

    def search(self, query, k=5, mode="hybrid", filters=None):
        """Return {"status", "best_dense_score", "results": [(chunk, score)]}; score type depends on mode."""
        if mode != "bm25" and not self.model:
            raise ValueError(f"mode={mode} needs a dense model")
        if mode == "bm25":
            ranked = self.bm25_ranking(query, filters)
        else:
            dense = self.dense_ranking(query, filters)
            ranked = dense if mode == "dense" else rrf([self.bm25_ranking(query, filters), dense])
        best = self.dense_ranking(query, filters, k=1) if self.model else []
        best = best[0][1] if best else None
        below_tau = self.model and self.tau is not None and (best is None or best < self.tau)
        status = "no_match" if below_tau or not ranked else "found"  # BM25 with no shared term returns nothing
        return {"status": status, "best_dense_score": best,
                "results": [] if status == "no_match" else [(self.chunks[i], s) for i, s in ranked[:k]]}


def rrf(rankings):
    fused = {}
    for ranking in rankings:
        for rank, (i, _) in enumerate(ranking, 1):
            fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(fused.items(), key=lambda x: -x[1])
