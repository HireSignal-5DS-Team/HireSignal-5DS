"""Load the two knowledge-base collections.

Job descriptions: rag/data/jobs/<job_id>.md, a front-matter header then the posting text verbatim:

    ---
    job_id: usajobs-123456
    title: Data Scientist
    organisation: ...
    source_url: https://...
    retrieved: 2026-10-13
    rights: public domain (US federal work) | reuse with attribution | ...
    ---
    <posting text, unedited>

ESCO: rag/data/esco/esco_ict_skills.jsonl, built by build_esco.py.
"""
import json
from pathlib import Path

DATA = Path(__file__).parent / "data"
REQUIRED = ("job_id", "title", "source_url", "retrieved", "rights")


def load_jobs(folder=DATA / "jobs"):
    jobs = []
    for p in sorted(folder.glob("*.md")):
        raw = p.read_text(encoding="utf-8")
        if not raw.startswith("---\n"):
            raise ValueError(f"{p.name}: missing front-matter header")
        head, body = raw[4:].split("\n---\n", 1)
        meta = dict(line.split(":", 1) for line in head.splitlines() if ":" in line)
        meta = {k.strip(): v.strip() for k, v in meta.items()}
        missing = [k for k in REQUIRED if not meta.get(k)]
        if missing:  # provenance is mandatory: no source, no indexing
            raise ValueError(f"{p.name}: missing provenance fields {missing}")
        jobs.append({**meta, "doc_id": meta["job_id"], "text": body.strip("\n")})
    return jobs


def load_esco(path=DATA / "esco/esco_ict_skills.jsonl"):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def build_chunks(strategy, jobs=None, esco=None):
    """Job chunks for one chunking strategy + ESCO entries (one entry = one chunk, never split)."""
    from chunking import STRATEGIES

    jobs = load_jobs() if jobs is None else jobs
    esco = load_esco() if esco is None else esco
    chunks = [c for job in jobs for c in STRATEGIES[strategy](job)]
    chunks += [{**e, "chunk_id": e["doc_id"], "section": None, "start": None, "end": None} for e in esco]
    return chunks
