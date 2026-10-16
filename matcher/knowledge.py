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


class QdrantKnowledge:
    """The team RAG's dense retriever (e5-small embeddings in Qdrant local mode, persisted index) over the ESCO
    collection, plus the job-posting collection when the job is one of the indexed postings (filter doc_id=job_id).
    Results are mapped with the RAG team's own rag/adapters.py:to_knowledge_refs. Note: the RAG team measured that
    dense ESCO retrieval does not improve the base Matcher on val (rag/integration/results/matcher_comparison.md);
    it is a selectable provider, not a default. CV text is never sent to retrieval."""
    name = "rag.qdrant.e5-small"
    uses_job = True

    def __init__(self, rag_dir=None, index_dir=None, retriever=None, k_job=2, min_job_score=0.0):
        rag_dir = Path(rag_dir or os.environ.get("HIRESIGNAL_RAG_DIR") or Path(__file__).parents[1] / "rag")
        sys.path.insert(0, str(rag_dir))
        from adapters import to_knowledge_refs  # RAG team's adapter

        self._to_refs, self.k_job, self.min_job_score = to_knowledge_refs, k_job, min_job_score
        if retriever is None:
            from corpus import build_chunks
            from retrieval import Retriever

            retriever = Retriever(build_chunks("structure"), model="e5-small", store_path=Path(index_dir or rag_dir / "index"))
        self.retriever = retriever
        self.job_ids = {c["doc_id"] for c in retriever.chunks if c.get("source_type") == "job"}

    def lookup(self, req, k=3, job_id=None):
        out = self.retriever.search(query_for(req), k=k, mode="dense", filters={"source_type": "esco"})
        refs = self._to_refs(out["results"], self.name)
        if job_id in self.job_ids and self.k_job:
            j = self.retriever.search(req.text, k=self.k_job, mode="dense", filters={"doc_id": job_id})
            refs += [r for r in self._to_refs(j["results"], self.name) if (r["relevance_score"] or 0) >= self.min_job_score]
        return [KnowledgeRef(**r) for r in refs]
