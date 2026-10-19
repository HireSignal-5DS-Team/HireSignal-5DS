# Adapted from team V2: rag/retrieval.py (BM25 path, RRF fusion idea) and matcher/knowledge.py (query_for) (feature/agent-integration @ a5a03ff)
"""Configurable ESCO retriever (T09): chunking A/B, BM25 / dense / hybrid (RRF), optional cross-encoder reranker,
optional ESCO graph expansion, dense vectors in numpy, Qdrant (local mode) or Chroma (persistent local).

Chunking (built from rag/data/esco/esco_ict_graph.jsonl):
  A  "<label>. Also known as: <alt labels>. <description>"  (= V2's text, what the Matcher has seen so far)
  B  A + " Broader: <labels>. Related: <labels>."            (labels of directly broader / related ESCO concepts)
The knowledge ref given to the Matcher is always the A text (format unchanged for the LoRA); B only changes what is
indexed. RAG output is KNOWLEDGE, never evidence: the query is the requirement (terms), never CV text.
"""
import json
import re
import time
from functools import lru_cache
from pathlib import Path

import bm25s
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "rag/data/esco/esco_ict_graph.jsonl"
CANDIDATES = 50   # V2 BM25 ranking depth
RRF_K = 60        # standard reciprocal-rank-fusion constant
RERANK_TOP = 20
# query / passage prefixes the model cards ask for
PREFIX = {"multilingual-e5-base": ("query: ", "passage: "),
          "bge-small-en-v1.5": ("Represent this sentence for searching relevant passages: ", "")}


def load_concepts(path=GRAPH):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def text_a(c):
    return (c["label"] + (". Also known as: " + "; ".join(c["alt_labels"]) if c["alt_labels"] else "") + ". "
            + c["description"]).strip()


def text_b(c):
    broader = [b["label"] for b in c["broader"]]
    related = [r["label"] for r in c["related"]]
    return (text_a(c) + (" Broader: " + "; ".join(broader) + "." if broader else "")
            + (" Related: " + "; ".join(related[:10]) + "." if related else ""))


def query_for(req):
    """req: dict with "text" and optional "skill_terms" (V2 matcher/knowledge.query_for)."""
    return " ".join(req["skill_terms"]) if req.get("skill_terms") else req["text"]


@lru_cache(maxsize=4)
def _encoder(name, device):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(str(ROOT / "models" / name), device=device)


@lru_cache(maxsize=2)
def _reranker(name, device):
    from sentence_transformers import CrossEncoder
    return CrossEncoder(str(ROOT / "models" / name), device=device)


class EscoRetriever:
    def __init__(self, chunking="A", search="bm25", embed=None, store="numpy", reranker=None, graph=False,
                 device="cpu", store_dir=None):
        if search not in ("bm25", "dense", "hybrid"):
            raise ValueError(search)
        if search != "bm25" and not embed:
            raise ValueError("dense / hybrid search need an embedding model")
        self.chunking, self.search, self.embed, self.store, self.rerank_model, self.graph = \
            chunking, search, embed, store, reranker, graph
        self.device = device
        self.concepts = load_concepts()
        self.index_of = {c["uri"]: i for i, c in enumerate(self.concepts)}
        self.texts = [(text_b if chunking == "B" else text_a)(c) for c in self.concepts]
        self.ref_texts = [text_a(c) for c in self.concepts]
        t = time.perf_counter()
        self.bm25 = bm25s.BM25()
        self.bm25.index(bm25s.tokenize(self.texts, stopwords="en", show_progress=False), show_progress=False)
        self.vectors = self._client = None
        if search != "bm25":
            q_pre, p_pre = PREFIX.get(embed, ("", ""))
            self.q_pre = q_pre
            self.vectors = np.asarray(_encoder(embed, device).encode([p_pre + x for x in self.texts], batch_size=64,
                                                                     normalize_embeddings=True, show_progress_bar=False))
            if store != "numpy":
                self._build_store(store, store_dir)
        self.build_s = round(time.perf_counter() - t, 2)
        self.name = f"esco/{chunking}/{search}" + (f"/{embed}/{store}" if search != "bm25" else "") + \
                    (f"/rerank:{reranker}" if reranker else "") + ("/graph" if graph else "")

    # ------------------------------------------------------------------ stores ---
    def _build_store(self, store, store_dir):
        store_dir = Path(store_dir or ROOT / "rag/index" / f"{store}_{self.chunking}_{self.embed}")
        store_dir.mkdir(parents=True, exist_ok=True)
        self.store_dir = store_dir
        payloads = [{"uri": c["uri"], "label": c["label"], "skill_type": c["skill_type"]} for c in self.concepts]
        if store == "qdrant":
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, PointStruct, VectorParams
            self._client = QdrantClient(path=str(store_dir))
            if self._client.collection_exists("esco"):
                self._client.delete_collection("esco")
            self._client.create_collection("esco", vectors_config=VectorParams(size=self.vectors.shape[1],
                                                                                distance=Distance.COSINE))
            self._client.upsert("esco", [PointStruct(id=i, vector=v.tolist(), payload=p)
                                         for i, (v, p) in enumerate(zip(self.vectors, payloads))])
        elif store == "chroma":
            import chromadb
            self._client = chromadb.PersistentClient(path=str(store_dir))
            try:
                self._client.delete_collection("esco")
            except Exception:  # noqa: BLE001  not there yet
                pass
            col = self._client.create_collection("esco", metadata={"hnsw:space": "cosine"})
            for i in range(0, len(self.texts), 500):  # Chroma batch limit
                col.add(ids=[str(j) for j in range(i, min(i + 500, len(self.texts)))],
                        embeddings=self.vectors[i:i + 500].tolist(), metadatas=payloads[i:i + 500])
            self._col = col
        else:
            raise ValueError(store)

    def _dense_ranking(self, query, n=CANDIDATES):
        q = np.asarray(_encoder(self.embed, self.device).encode([self.q_pre + query], normalize_embeddings=True,
                                                                show_progress_bar=False))[0]
        if self.store == "numpy":
            s = self.vectors @ q
            order = np.argsort(-s)[:n]
            return [(int(i), float(s[i])) for i in order]
        if self.store == "qdrant":
            hits = self._client.query_points("esco", query=q.tolist(), limit=n).points
            return [(int(h.id), float(h.score)) for h in hits]
        res = self._col.query(query_embeddings=[q.tolist()], n_results=n)
        return [(int(i), 1 - float(d)) for i, d in zip(res["ids"][0], res["distances"][0])]

    def _bm25_ranking(self, query, n=CANDIDATES):
        tokens = bm25s.tokenize(query, stopwords="en", show_progress=False, return_ids=False)[0]
        s = self.bm25.get_scores(tokens) if tokens else np.zeros(len(self.texts))
        order = np.argsort(-s)[:n]
        return [(int(i), float(s[i])) for i in order if np.isfinite(s[i]) and s[i] > 0]

    # ------------------------------------------------------------------ search ---
    def ranking(self, query, n=10):
        """[(concept index, score)] best first."""
        if self.search == "bm25":
            ranked = self._bm25_ranking(query)
        elif self.search == "dense":
            ranked = self._dense_ranking(query)
        else:  # hybrid: reciprocal rank fusion of the two top-50 lists
            fused = {}
            for lst in (self._bm25_ranking(query), self._dense_ranking(query)):
                for rank, (i, _) in enumerate(lst):
                    fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank + 1)
            ranked = sorted(fused.items(), key=lambda x: -x[1])
        if self.rerank_model and ranked:
            top = ranked[:RERANK_TOP]
            scores = _reranker(self.rerank_model, self.device).predict([(query, self.ref_texts[i]) for i, _ in top],
                                                                        show_progress_bar=False)
            ranked = sorted(((i, float(s)) for (i, _), s in zip(top, scores)), key=lambda x: -x[1]) + ranked[RERANK_TOP:]
        if self.graph:
            ranked = self._expand(ranked)
        return ranked[:n]

    def _expand(self, ranked, seeds=3):
        """ESCO graph expansion: after each of the top `seeds` hits, insert its broader and related concepts that are
        in the corpus (and not already ranked above), with the parent's score."""
        out, seen = [], set()
        for pos, (i, s) in enumerate(ranked):
            if i in seen:
                continue
            out.append((i, s))
            seen.add(i)
            if pos < seeds:
                c = self.concepts[i]
                for link in c["broader"] + c["related"]:
                    j = self.index_of.get(link["uri"])
                    if j is not None and j not in seen:
                        out.append((j, s))
                        seen.add(j)
        return out

    def lookup(self, req, k=3, max_chars=300):
        """Knowledge refs for the Matcher: [{source_id, title, text (A text, <= max_chars), url, aliases, relevance_score}].
        max_chars 300 = what V2 p1 format_knowledge (and our V0) shows the LoRA."""
        out = []
        for i, s in self.ranking(query_for(req), n=k):
            c = self.concepts[i]
            out.append({"source_id": c["uri"], "title": c["label"], "text": self.ref_texts[i][:max_chars], "url": c["uri"],
                        "aliases": c["alt_labels"], "relevance_score": round(s, 4)})
        return out


def terms_in_cv(req, cv_text):
    """True when every skill term (or, without terms, the requirement text) occurs literally in the CV
    (case-insensitive, whole word): then no knowledge is needed (Locked RAG rule, variant V6)."""
    terms = req.get("skill_terms") or []
    if not terms:
        return False
    return all(re.search(rf"(?<![\w+#]){re.escape(t)}(?![\w+#])", cv_text, re.I) for t in terms)
