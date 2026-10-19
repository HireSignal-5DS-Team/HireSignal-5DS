# Adapted from team V2: matcher/knowledge.py (RagKnowledge, query_for, esco_aliases), rag/retrieval.py (Retriever BM25 path), rag/corpus.py (load_esco) (feature/agent-integration @ a5a03ff)
"""BM25 knowledge over ESCO ICT skills: the exact `rag.bm25` provider V2 used for its Matcher runs (k=3).

Kept only the BM25 path: tokenize with bm25s English stopwords, score every ESCO entry, keep positive scores,
return the top k. Only the requirement's skill terms (or its text) are sent as the query; CV text never is.
Output is KNOWLEDGE (what a skill means / other names), never evidence about a candidate.
"""
import hashlib
import json
import re
from pathlib import Path

import bm25s
import numpy as np

NAME = "rag.bm25"
DEFAULT_ESCO = Path(__file__).parent / "data" / "esco" / "esco_ict_skills.jsonl"
CANDIDATES = 50  # V2 rag/retrieval.py CANDIDATES (BM25 ranking depth)

_AKA = re.compile(r"Also known as: (.*?)\.\s", re.S)


def esco_aliases(text):
    m = _AKA.search(text + " ")
    return [a.strip() for a in m.group(1).split(";") if a.strip()] if m else []


def query_for(req):
    """req: dict with "text" and optional "skill_terms"."""
    return " ".join(req["skill_terms"]) if req.get("skill_terms") else req["text"]


class BM25EscoKnowledge:
    name = NAME

    def __init__(self, esco_path=DEFAULT_ESCO, min_score=0.0):
        esco_path = Path(esco_path)
        with open(esco_path, encoding="utf-8") as f:
            self.entries = [json.loads(line) for line in f]
        self.bm25 = bm25s.BM25()
        self.bm25.index(bm25s.tokenize([e["text"] for e in self.entries], stopwords="en", show_progress=False),
                        show_progress=False)
        self.min_score = min_score
        sha12 = hashlib.sha256(esco_path.read_bytes()).hexdigest()[:12]
        self.version = f"bm25s-{bm25s.__version__};esco={sha12};min_score={min_score}"

    def _ranking(self, query):
        tokens = bm25s.tokenize(query, stopwords="en", show_progress=False, return_ids=False)[0]
        scores = self.bm25.get_scores(tokens) if tokens else np.zeros(len(self.entries))
        order = np.argsort(-scores)[:CANDIDATES]
        return [(int(i), float(scores[i])) for i in order if np.isfinite(scores[i]) and scores[i] > 0]

    def lookup(self, req, k=3):
        """List of {source_id, title, text, url, aliases, relevance_score}; empty list = nothing relevant."""
        out = []
        for i, score in self._ranking(query_for(req))[:k]:
            if score <= self.min_score:
                continue
            e = self.entries[i]
            out.append({"source_id": e["doc_id"], "title": e["title"], "text": e["text"], "url": e["url"],
                        "aliases": esco_aliases(e["text"]), "relevance_score": round(score, 4)})
        return out
