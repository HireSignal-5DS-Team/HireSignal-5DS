"""Knowledge providers for the Matcher. Retrieval is lexical (BM25) so the Matcher stays a one-neural-model system.

Frozen interface v1 (docs/orchestration/ORCHESTRATION.md §3): lookup(req, k=3, job_id=None) -> list[KnowledgeRef].
An empty list is an abstention. Every provider here accepts job_id (ignored when it has no job collection).

- GatedKnowledge (rag.gated.v1, S1, docs/rag/RAG_OPTIMIZATION.md): requirement-type gating, exact ESCO label/alias
  match first, strict lexical relevance cut-off otherwise, at most one concept per skill term, de-duplication,
  compact knowledge text (<= 280 chars, always shown whole by the p1 prompt, so rag_refs cite only shown text).
  BM25 candidates by default (no model); pass a dense Retriever (Qdrant + e5-small) for dense candidates.
- RagKnowledge: legacy arm (B/B′ runs): the team's RAG (rag/retrieval.py, branch claude/gracious-fermi-ncuem4) in BM25 mode over the ESCO
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


def file_sha12(path):
    """First 12 hex chars of the SHA-256 of a data file (provider `version` strings for provenance)."""
    import hashlib

    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
    except OSError:
        return "missing"


def _bm25s_version():
    try:
        from importlib.metadata import version

        return version("bm25s")
    except Exception:  # noqa: BLE001 - provenance only
        return "unknown"


def query_for(req):
    return " ".join(req.skill_terms) if req.skill_terms else req.text


class FixtureKnowledge:
    name = "fixture"
    version = "fixture"

    def __init__(self, entries):
        """entries: list of dicts {source_id, title, aliases, text}; matched when title or alias occurs in the query."""
        self.entries = entries

    def lookup(self, req, k=3, job_id=None):
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
        self.version = f"bm25s-{_bm25s_version()};esco={file_sha12(rag_dir / 'data/esco/esco_ict_skills.jsonl')};min_score={min_score}"

    def lookup(self, req, k=3, job_id=None):
        out = self.retriever.search(query_for(req), k=k, mode="bm25", filters={"source_type": "esco"})
        return [KnowledgeRef(source_type="esco", source_id=c["doc_id"], title=c["title"], text=c["text"], url=c["url"],
                             aliases=esco_aliases(c["text"]), relevance_score=round(s, 4), retrieval=self.name)
                for c, s in out["results"] if s > self.min_score]


class NoKnowledge:
    name = "none"
    version = "none"

    def lookup(self, req, k=3, job_id=None):
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
        self.version = (f"e5-small;index={getattr(retriever, 'collection', 'n/a')};"
                        f"esco={file_sha12(rag_dir / 'data/esco/esco_ict_skills.jsonl')};k_job={k_job}")

    def lookup(self, req, k=3, job_id=None):
        out = self.retriever.search(query_for(req), k=k, mode="dense", filters={"source_type": "esco"})
        refs = self._to_refs(out["results"], self.name)
        if job_id in self.job_ids and self.k_job:
            j = self.retriever.search(req.text, k=self.k_job, mode="dense", filters={"doc_id": job_id})
            refs += [r for r in self._to_refs(j["results"], self.name) if (r["relevance_score"] or 0) >= self.min_job_score]
        return [KnowledgeRef(**r) for r in refs]


# --- rag.gated.v1 (S1) -------------------------------------------------------------------------------------------
# Design and measurements: docs/rag/RAG_OPTIMIZATION.md. Retrieval sees requirement text / skill terms only.

GATED_VERSION = "rag.gated.v1"
# ESCO (ICT subset) holds skill concepts only: no credentials, CEFR levels or degrees. On val these requirement types
# got only off-target concepts (e.g. "SQL Server" for an Azure certification) and lost accuracy with RAG.
NO_KNOWLEDGE_CATEGORIES = frozenset({"certification", "language", "education"})
MAX_TEXT_CHARS = 280  # matcher/prompt.py (p1) shows the first 300 chars of a ref: stay below, so a ref is shown whole
PROMPT_TAG_CHARS = 12  # p1 tags each ref with source_id.rsplit("/", 1)[-1][:12]
_STOP = frozenset(
    "a an and the of in for to with on at by or from as is are be into over than via using use used "
    "ability able strong proven solid working knowledge experience experienced hands proficiency proficient "
    "background skill skills good excellent understanding familiarity familiar expertise demonstrated "
    "professional least minimum min year years yrs more plus".split())
_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#]*(?:\.[a-z0-9]+)*")


def _stem(t):
    for suf, keep in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if len(t) > len(suf) + 3 and t.endswith(suf) and not t.endswith("ss"):
            return t[: -len(suf)] + keep
    return t


def surface(s):
    """Normalised surface form used for exact label/alias matching (case, spacing, '-'/'_' insensitive)."""
    return " ".join(_TOKEN.findall(s.casefold().replace("-", " ").replace("_", " ")))


def content_tokens(s):
    return {_stem(t) for t in _TOKEN.findall(s.casefold().replace("-", " ")) if t not in _STOP and not t.isdigit()}


def esco_description(text, title):
    """ESCO entry text = '<title>. Also known as: a; b. <description>' -> description."""
    m = _AKA.search(text + " ")
    if m:
        return text[m.end():].strip()
    return text[len(title) + 1:].strip() if text.startswith(title + ".") else text


def distinct_aliases(title, aliases):
    """Drop aliases that only repeat the title or an earlier alias up to case/inflection (de-duplication)."""
    seen, out = {frozenset(content_tokens(title)) or surface(title)}, []
    for a in aliases:
        key = frozenset(content_tokens(a)) or surface(a)
        if key not in seen:
            seen.add(key)
            out.append(a)
    return out


def _clip(s, n):
    if len(s) <= n:
        return s
    cut = s[: max(0, n - 3)].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "..." if cut else ""


def compact_text(title, aliases, description, max_chars=MAX_TEXT_CHARS, alias_budget=190):
    """Short knowledge text: title, as many distinct aliases as fit, then the start of the description.
    Returns (text, aliases actually shown)."""
    head, shown = f"{title}.", []
    for a in distinct_aliases(title, [" ".join(a.split()) for a in aliases]):
        if len(f"{head} Also known as: {'; '.join([*shown, a])}.") > alias_budget:
            break
        shown.append(a)
    text = head + (f" Also known as: {'; '.join(shown)}." if shown else "")
    room = max_chars - len(text) - 1
    if description and room >= 25:
        desc = _clip(" ".join(description.split()), room)
        text += f" {desc}" if desc else ""
    return text[:max_chars], shown


class GatedKnowledge:
    """rag.gated.v1: abstain unless the knowledge base holds the required concept itself.

    1. Gate: requirement categories in NO_KNOWLEDGE_CATEGORIES -> [] (prompt identical to the no-RAG prompt).
    2. Query = the requirement's skill terms (the requirement sentence when it has none; never CV text).
    3. Exact ESCO preferred-label / alternative-label match. Without skill terms: the label inside the sentence that
       covers all its content words (sentence_min_cover=1.0; stop words and template words like "ability to" are
       ignored). Ambiguous surface forms prefer the concept whose preferred label it is.
    4. Otherwise retriever candidates (BM25, or dense through Qdrant) pass a relevance cut-off: one of the
       candidate's labels (preferred or alternative) must contain every content token of the query (stop words and
       inflection ignored) and at most `max_extra` other content tokens (default 0, i.e. the same words in any
       order); with a dense retriever a candidate may instead pass on cosine >= dense_tau (calibrated ESCO
       threshold of the RAG team, exp03).
    5. At most `per_term` concept(s) per skill term (default 1: neighbouring concepts are dropped), de-duplicated by
       source_id and by prompt tag, total <= k.
    6. Compact text (<= MAX_TEXT_CHARS): the p1 prompt shows each ref whole, so rag_refs cite only shown text.
    7. job_id among the indexed postings: one trimmed passage of that posting (<= MAX_TEXT_CHARS) that shares a
       content token with the requirement, within the k budget.
    """
    uses_job = True

    def __init__(self, rag_dir=None, retriever=None, mode="bm25", per_term=1, max_extra=0, dense_tau=None,
                 gate=NO_KNOWLEDGE_CATEGORIES, k_job=1, candidates=10, esco=None, sentence_min_cover=1.0):
        rag_dir = Path(rag_dir or os.environ.get("HIRESIGNAL_RAG_DIR") or Path(__file__).parents[1] / "rag")
        if str(rag_dir) not in sys.path:
            sys.path.insert(0, str(rag_dir))
        if retriever is None:
            from corpus import build_chunks
            from retrieval import Retriever

            retriever = Retriever(build_chunks("structure"))  # BM25 only: no embedding model
        if mode != "bm25" and not getattr(retriever, "model", None):
            raise ValueError(f"mode={mode} needs a dense Retriever (model='e5-small')")
        self.retriever, self.mode = retriever, mode
        self.per_term, self.max_extra, self.dense_tau = per_term, max_extra, dense_tau
        self.gate, self.k_job, self.candidates = frozenset(gate), k_job, candidates
        self.sentence_min_cover = sentence_min_cover
        if esco is None:
            esco = [c for c in retriever.chunks if c.get("source_type") == "esco"]
        self.esco = {e["doc_id"]: e for e in esco}
        self.surface_index = {}
        for e in esco:  # preferred labels first, so they win over another concept's alternative label
            self.surface_index.setdefault(surface(e["title"]), []).append(e["doc_id"])
        for e in esco:
            for a in esco_aliases(e["text"]):
                ids = self.surface_index.setdefault(surface(a), [])
                if e["doc_id"] not in ids:
                    ids.append(e["doc_id"])
        self.form_tokens = {e["doc_id"]: [content_tokens(x) for x in [e["title"], *esco_aliases(e["text"])]] for e in esco}
        self.job_ids = {c["doc_id"] for c in retriever.chunks if c.get("source_type") == "job"}
        self.name = f"{GATED_VERSION}+{'bm25' if mode == 'bm25' else 'qdrant.' + str(getattr(retriever, 'collection', mode))}"
        self.version = (f"{GATED_VERSION};retriever={'bm25s-' + _bm25s_version() if mode == 'bm25' else 'qdrant.' + str(getattr(retriever, 'collection', mode))};"
                        f"esco={file_sha12(rag_dir / 'data/esco/esco_ict_skills.jsonl')};tau={dense_tau};max_extra={max_extra};"
                        f"per_term={per_term};sentence_min_cover={sentence_min_cover};gate={','.join(sorted(self.gate))};"
                        f"max_chars={MAX_TEXT_CHARS}")
        self.last_trace = None

    # -- concept selection --
    def _exact(self, phrase):
        return list(self.surface_index.get(surface(phrase), []))

    def _exact_in_sentence(self, text):
        """The ESCO surface form inside the sentence that covers the largest share of the sentence's content words
        (ties: the longer form); kept only if that share >= sentence_min_cover. One concept group at most, so a
        sentence such as "database design" does not return "database" and "design" as two separate concepts."""
        words, q = surface(text).split(), content_tokens(text)
        best = None
        for n in range(len(words), 0, -1):
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i:i + n])
                toks = content_tokens(phrase)
                if phrase in self.surface_index and toks and q:
                    key = (len(toks & q) / len(q), n)
                    if best is None or key > best[0]:
                        best = (key, self.surface_index[phrase])
        return [best[1]] if best and best[0][0] >= self.sentence_min_cover else []

    def _fuzzy(self, query):
        q = content_tokens(query)
        if not q:
            return []
        out = self.retriever.search(query, k=self.candidates, mode=self.mode, filters={"source_type": "esco"})
        keep = []
        for c, score in out["results"]:
            lexical_ok = any(q <= f and len(f - q) <= self.max_extra for f in self.form_tokens.get(c["doc_id"], []))
            dense_ok = self.mode != "bm25" and self.dense_tau is not None and score >= self.dense_tau
            if lexical_ok or dense_ok:
                keep.append(c["doc_id"])
        return keep

    def _ref(self, doc_id, how):
        e = self.esco[doc_id]
        text, shown = compact_text(e["title"], esco_aliases(e["text"]), esco_description(e["text"], e["title"]))
        return KnowledgeRef(source_type="esco", source_id=doc_id, title=e["title"], text=text, url=e.get("url"),
                            aliases=shown, relevance_score=1.0 if how == "exact" else None,
                            retrieval=f"{self.name}:{how}")

    def _job_ref(self, req, job_id):
        q = content_tokens(query_for(req) + " " + req.text)
        out = self.retriever.search(req.text, k=1, mode=self.mode, filters={"doc_id": job_id})
        for c, score in out["results"]:
            body = c["text"].split("\n", 1)[-1]
            sents = re.findall(r"\S.*?(?:[.!?;](?=\s|$)|$)", body, re.S)
            best = max(range(len(sents)), key=lambda i: len(q & content_tokens(sents[i])), default=None)
            if best is None or not q & content_tokens(sents[best]):
                return None  # relevance cut-off: the passage shares no content word with the requirement
            head = f"Job posting, section {c.get('section') or 'n/a'}: "
            return KnowledgeRef(source_type="job", source_id=c.get("chunk_id") or c["doc_id"], title=c["title"],
                                text=head + _clip(" ".join(sents[best].split()), MAX_TEXT_CHARS - len(head)),
                                url=c.get("url"), relevance_score=round(float(score), 4),
                                retrieval=f"{self.name}:job")
        return None

    def lookup(self, req, k=3, job_id=None):
        trace = {"req_id": req.req_id, "category": req.category, "gated": req.category in self.gate, "terms": []}
        self.last_trace = trace
        if trace["gated"] or k <= 0:
            return []
        groups = []
        if req.skill_terms:
            for t in req.skill_terms:
                ids, how = self._exact(t), "exact"
                if not ids:
                    ids, how = self._fuzzy(t), "cutoff"
                groups.append((ids, how))
                trace["terms"].append({"term": t, "how": how if ids else "abstain", "candidates": ids[:5]})
        else:
            groups = [(ids, "exact") for ids in self._exact_in_sentence(req.text)]
            if not groups:
                groups = [(self._fuzzy(req.text), "cutoff")]
            trace["terms"].append({"term": req.text, "how": groups[0][1] if groups[0][0] else "abstain"})
        k_esco = k - (1 if job_id in self.job_ids and self.k_job else 0)
        refs, seen_ids, seen_tags = [], set(), set()
        for ids, how in groups:
            for doc_id in ids[: self.per_term]:
                tag = doc_id.rsplit("/", 1)[-1][:PROMPT_TAG_CHARS]
                if doc_id in seen_ids or tag in seen_tags or len(refs) >= k_esco:
                    continue
                seen_ids.add(doc_id)
                seen_tags.add(tag)
                refs.append(self._ref(doc_id, how))
        if job_id in self.job_ids and self.k_job and len(refs) < k:
            j = self._job_ref(req, job_id)
            if j is not None and j.source_id.rsplit("/", 1)[-1][:PROMPT_TAG_CHARS] not in seen_tags:
                refs.append(j)
        trace["n_refs"] = len(refs)
        return refs
