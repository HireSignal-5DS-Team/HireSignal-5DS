"""Seven chunking strategies for job postings. All return character offsets into the posting body, so every
strategy is scored against the same gold spans. `structure` and `sliding` are the production module's functions,
imported unchanged (rag/chunking.py: its "fixed" strategy is a 200/30 sliding window)."""
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[2]))
from chunking import fixed_chunks as sliding_chunks  # noqa: E402  200 words, 30 overlap
from chunking import structure_chunks  # noqa: E402

WORDS = 200          # target size shared by fixed, sliding and recursive (~260 subword tokens)
SENTS_PER_CHUNK = 5  # sentence-based
SEM_PERCENTILE = 25  # semantic: break where adjacent-sentence similarity is in the lowest 25% of the posting
SEM_MAX_WORDS = 300  # semantic: hard cap so a chunk never exceeds the embedder's input length by much
SENT = re.compile(r"\S.*?(?:[.!?]+(?=\s|$)|\n|$)", re.S)  # shortcut: no abbreviation handling ("e.g." splits)


def _chunk(job, name, i, s, e, text=None, **extra):
    body = job["text"]
    return {"chunk_id": f"{job['doc_id']}#{name}-{i}", "doc_id": job["doc_id"], "source_type": "job",
            "title": job["title"], "url": job.get("source_url"), "section": extra.pop("section", None),
            "start": s, "end": e, "text": text if text is not None else body[s:e], **extra}


def _words(body, s, e):
    return len(body[s:e].split())


def sentences(body, s=0, e=None):
    e = len(body) if e is None else e
    return [(s + m.start(), s + m.start() + len(m.group().rstrip())) for m in SENT.finditer(body[s:e]) if m.group().strip()]


def fixed_chunks(job):
    body = job["text"]
    w = [m.span() for m in re.finditer(r"\S+", body)]
    return [_chunk(job, "fixed", n, w[i][0], w[min(i + WORDS, len(w)) - 1][1]) for n, i in enumerate(range(0, len(w), WORDS))]


def recursive_chunks(job):
    """LangChain-style: split on paragraphs, then lines, then sentences, then words; merge neighbours up to WORDS."""
    body = job["text"]
    seps = [r"\n\s*\n", r"\n", None, r"\s+"]  # None = sentence boundaries

    def split(s, e, level):
        if _words(body, s, e) <= WORDS or level == len(seps):
            return [(s, e)]
        if seps[level] is None:
            pieces = sentences(body, s, e)
        else:
            cuts = [s] + [s + m.end() for m in re.finditer(seps[level], body[s:e])] + [e]
            pieces = [(a, b) for a, b in zip(cuts, cuts[1:]) if body[a:b].strip()]
        out, cur = [], None
        for a, b in pieces:
            if _words(body, a, b) > WORDS:
                out += ([cur] if cur else []) + split(a, b, level + 1)
                cur = None
            elif cur and _words(body, cur[0], b) <= WORDS:
                cur = (cur[0], b)
            else:
                out += [cur] if cur else []
                cur = (a, b)
        return out + ([cur] if cur else [])

    return [_chunk(job, "recursive", i, s, e) for i, (s, e) in enumerate(split(0, len(body), 0))]


def sentence_chunks(job):
    sents = sentences(job["text"])
    return [_chunk(job, "sentence", n, sents[i][0], sents[min(i + SENTS_PER_CHUNK, len(sents)) - 1][1])
            for n, i in enumerate(range(0, len(sents), SENTS_PER_CHUNK))]


def semantic_chunks(job, encode):
    """Embed sentences; start a new chunk where similarity to the previous sentence is unusually low."""
    body = job["text"]
    sents = sentences(body)
    if len(sents) < 2:
        return [_chunk(job, "semantic", 0, 0, len(body))]
    v = encode([body[s:e] for s, e in sents])
    sims = (v[:-1] * v[1:]).sum(1)
    cut = np.percentile(sims, SEM_PERCENTILE)
    groups, start = [], 0
    for i in range(1, len(sents)):
        if sims[i - 1] < cut or _words(body, sents[start][0], sents[i][1]) > SEM_MAX_WORDS:
            groups.append((sents[start][0], sents[i - 1][1]))
            start = i
    groups.append((sents[start][0], sents[-1][1]))
    return [_chunk(job, "semantic", i, s, e) for i, (s, e) in enumerate(groups)]


def parent_child_chunks(job):
    """Children = single sentences (with the parent's Job/Section header) are matched; the parent (structure
    section chunk) is what gets returned and scored."""
    out = []
    for p in structure_chunks(job):
        head = p["text"].split("\n", 1)[0]
        for s, e in sentences(job["text"], p["start"], p["end"]):
            out.append(_chunk(job, "child", len(out), s, e, f"{head}\n{job['text'][s:e]}", section=p["section"],
                              parent_id=p["chunk_id"], parent_start=p["start"], parent_end=p["end"],
                              parent_text=p["text"]))
    return out


CHUNKERS = {"fixed": fixed_chunks, "structure": structure_chunks, "recursive": recursive_chunks,
            "semantic": semantic_chunks, "sliding": sliding_chunks, "sentence": sentence_chunks,
            "parent_child": parent_child_chunks}
NEEDS_ENCODER = {"semantic"}


def coverage(job, chunks):
    """Share of the posting's non-space characters that fall inside at least one chunk."""
    body = job["text"]
    cov = np.zeros(len(body), bool)
    for c in chunks:
        cov[c["start"]:c["end"]] = True
    ns = np.array([not ch.isspace() for ch in body])
    return float(cov[ns].mean())
