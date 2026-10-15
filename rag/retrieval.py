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
    "e5-base": ("intfloat/multilingual-e5-base", "query: ", "passage: ", None),
}
RERANKERS = {"mmarco": "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1", "bge": "BAAI/bge-reranker-v2-m3"}


class Retriever:
    def __init__(self, chunks, model=None, store_path=None, tau=None, reranker=None, top_n=10, thresholds=None):
        """reranker: optional cross-encoder name (RERANKERS) applied to the top_n first-stage results.
        thresholds: optional {"job": t, "esco": t} abstention cut-offs on the reranker score (cosine without reranker),
        calibrated per collection on a separate split. Defaults reproduce the original behaviour."""
        self.chunks = chunks
        self.reranker, self.top_n, self.thresholds = reranker, top_n, thresholds or {}
        self._ce = None
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
        # collection name fingerprints model + chunk texts, so a changed corpus is re-embedded
        digest = hashlib.sha1("".join(c["chunk_id"] + c["text"] for c in self.chunks).encode()).hexdigest()[:12]
        self.collection = f"{model}-{digest}"
        self.index_recovered_from = None
        try:
            self.qdrant = QdrantClient(path=str(store_path)) if store_path else QdrantClient(":memory:")
            self.index_reused = self.qdrant.collection_exists(self.collection)  # embeddings persisted by a previous run
            if self.index_reused:
                self.qdrant.count(self.collection)  # touches the storage file: fails here if it is corrupted
        except Exception as err:  # unreadable index: keep it aside for inspection, rebuild (embeddings are derived data)
            if not store_path:
                raise
            import shutil
            import time
            self.index_recovered_from = f"{store_path}.corrupt-{int(time.time())}"
            shutil.move(str(store_path), self.index_recovered_from)
            print(f"WARNING: index at {store_path} unreadable ({type(err).__name__}); moved to "
                  f"{self.index_recovered_from}, rebuilding", flush=True)
            self.qdrant = QdrantClient(path=str(store_path))
            self.index_reused = False
        if not self.index_reused:
            vecs = self.model.encode([p_prefix + c["text"] for c in self.chunks], normalize_embeddings=True,
                                     batch_size=32, show_progress_bar=True)
            self.qdrant.create_collection(self.collection, vectors_config=models.VectorParams(
                size=vecs.shape[1], distance=models.Distance.COSINE))
            self.qdrant.upload_collection(self.collection, vectors=vecs, ids=range(len(self.chunks)),
                                          payload=[{"doc_id": c["doc_id"], "source_type": c["source_type"]}
                                                   for c in self.chunks])

    def close(self):
        """Release the on-disk index (Qdrant local mode allows one process per folder)."""
        if self.model:
            self.qdrant.close()

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
        """Return {"status", "best_dense_score", "rerank_score", "results": [(chunk, score)]}; score type depends on mode."""
        if mode != "bm25" and not self.model:
            raise ValueError(f"mode={mode} needs a dense model")
        depth = 200 if "parent_id" in self.chunks[0] else CANDIDATES  # many children per returned parent
        if mode == "bm25":
            ranked = self.bm25_ranking(query, filters, k=depth)
        else:
            dense = self.dense_ranking(query, filters, k=depth)
            ranked = dense if mode == "dense" else rrf([self.bm25_ranking(query, filters, k=depth), dense])
        if self.model and mode == "bm25":
            dense = self.dense_ranking(query, filters, k=1)
        best = dense[0][1] if self.model and dense else None
        units = self._units(ranked)
        top_rr = None
        if self.reranker and units:
            head = units[:self.top_n]
            scores = self._cross_encoder().predict([(query, c["text"]) for c, _ in head], batch_size=16)
            order = np.argsort(-scores)
            top_rr = float(scores[order[0]])
            units = [(head[i][0], float(scores[i])) for i in order] + units[self.top_n:]
        below_tau = self.model and self.tau is not None and (best is None or best < self.tau)
        coll = "job" if (filters or {}).get("doc_id") or (filters or {}).get("source_type") == "job" else "esco"
        cut = self.thresholds.get(coll)
        abstain_score = top_rr if top_rr is not None else best
        below_cut = cut is not None and (abstain_score is None or abstain_score < cut)
        status = "no_match" if below_tau or below_cut or not units else "found"  # BM25 with no shared term returns nothing
        return {"status": status, "best_dense_score": best, "rerank_score": top_rr,
                "results": [] if status == "no_match" else units[:k]}

    def _units(self, ranked):
        """(chunk, score) list; parent-child children are collapsed into their parent section (first hit wins)."""
        out, seen = [], set()
        for i, score in ranked:
            c = self.chunks[i]
            if "parent_id" in c:
                if c["parent_id"] in seen:
                    continue
                seen.add(c["parent_id"])
                c = {**c, "chunk_id": c["parent_id"], "start": c["parent_start"], "end": c["parent_end"], "text": c["parent_text"]}
            out.append((c, score))
        return out

    def _cross_encoder(self):
        if self._ce is None:
            from sentence_transformers import CrossEncoder
            self._ce = CrossEncoder(RERANKERS[self.reranker], device="cpu", max_length=512)
        return self._ce


def rrf(rankings):
    fused = {}
    for ranking in rankings:
        for rank, (i, _) in enumerate(ranking, 1):
            fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(fused.items(), key=lambda x: -x[1])
