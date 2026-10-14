"""Knowledge providers for the Matcher. Retrieval is lexical (BM25) so the Matcher stays a one-neural-model system.

- RagKnowledge: the team's RAG (rag/retrieval.py, branch claude/gracious-fermi-ncuem4) in BM25 mode over the ESCO
  collection. Located via HIRESIGNAL_RAG_DIR or <repo>/rag. Only requirement text / skill terms are sent as
  queries; CV text is never sent to retrieval.
- FixtureKnowledge: deterministic in-memory entries for tests and offline benchmarks.
"""
import os
import re
import sys
from pathlib import Path

from .schemas import KnowledgeRef

_AKA = re.compile(r"Also known as: (.*?)\.\s", re.S)


def esco_aliases(text):
    m = _AKA.search(text + " ")
    return [a.strip() for a in m.group(1).split(";") if a.strip()] if m else []


def query_for(req):
    return " ".join(req.skill_terms) if req.skill_terms else req.text


class FixtureKnowledge:
    name = "fixture"

    def __init__(self, entries):
        """entries: list of dicts {source_id, title, aliases, text}; matched when title or alias occurs in the query."""
        self.entries = entries

    def lookup(self, req, k=3):
        q = (query_for(req) + " " + req.text).casefold()
        hits = [e for e in self.entries if any(t.casefold() in q for t in [e["title"], *e.get("aliases", [])])]
        return [KnowledgeRef(source_type=e.get("source_type", "fixture"), source_id=e["source_id"], title=e["title"],
                             text=e["text"], aliases=e.get("aliases", []), url=e.get("url"),
                             retrieval="fixture.term_match") for e in hits[:k]]


class RagKnowledge:
    name = "rag.bm25"

    def __init__(self, rag_dir=None, min_score=0.0):
        rag_dir = Path(rag_dir or os.environ.get("HIRESIGNAL_RAG_DIR") or Path(__file__).parents[1] / "rag")
        if not (rag_dir / "retrieval.py").exists():
            raise FileNotFoundError(f"RAG code not found in {rag_dir}; set HIRESIGNAL_RAG_DIR")
        sys.path.insert(0, str(rag_dir))
        from corpus import load_esco  # noqa: E402  (RAG modules)
        from retrieval import Retriever

        esco = load_esco(rag_dir / "data/esco/esco_ict_skills.jsonl")
        chunks = [{**e, "chunk_id": e["doc_id"], "section": None, "start": None, "end": None} for e in esco]
        self.retriever = Retriever(chunks)  # model=None -> BM25 only, no embedding model
        self.min_score = min_score

    def lookup(self, req, k=3):
        out = self.retriever.search(query_for(req), k=k, mode="bm25", filters={"source_type": "esco"})
        return [KnowledgeRef(source_type="esco", source_id=c["doc_id"], title=c["title"], text=c["text"], url=c["url"],
                             aliases=esco_aliases(c["text"]), relevance_score=round(s, 4), retrieval=self.name)
                for c, s in out["results"] if s > self.min_score]


class NoKnowledge:
    name = "none"

    def lookup(self, req, k=3):
        return []
