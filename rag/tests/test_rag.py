import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from chunking import FIXED_WORDS, fixed_chunks, structure_chunks  # noqa: E402
from corpus import build_chunks, load_jobs  # noqa: E402
from retrieval import Retriever, rrf  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def job():
    return load_jobs(FIX)[0]


def test_structure_chunks_follow_headings(job):
    chunks = structure_chunks(job)
    assert [c["section"] for c in chunks] == ["About the role", "Responsibilities", "Requirements", "Nice to have"]
    req = chunks[2]
    assert "2 years of experience with SQL" in job["text"][req["start"]:req["end"]]
    assert "Spark" not in job["text"][req["start"]:req["end"]]  # must-have and nice-to-have stay separate
    assert req["text"].startswith("Job: Junior Data Scientist | Section: Requirements")


def test_fixed_chunks_offsets_and_overlap():
    words = " ".join(f"w{i}" for i in range(500))
    chunks = fixed_chunks({"doc_id": "d", "title": "t", "text": words})
    assert all(c["text"] == words[c["start"]:c["end"]] for c in chunks)
    assert len(chunks[0]["text"].split()) == FIXED_WORDS
    assert chunks[1]["start"] < chunks[0]["end"]  # windows overlap
    assert chunks[-1]["end"] == len(words)  # nothing dropped at the end


def test_missing_provenance_rejected(tmp_path):
    (tmp_path / "x.md").write_text("---\njob_id: x\ntitle: t\n---\nbody")
    with pytest.raises(ValueError, match="provenance"):
        load_jobs(tmp_path)


def test_bm25_filtered_search(job):
    esco = [{"doc_id": "esco:sql", "source_type": "esco", "title": "SQL", "text": "SQL. Query language."}]
    r = Retriever(build_chunks("structure", [job], esco))
    out = r.search("required experience SQL Python", mode="bm25", filters={"doc_id": job["doc_id"]})
    assert out["results"][0][0]["section"] == "Requirements"
    assert all(c["source_type"] == "job" for c, _ in out["results"])


def test_rrf_rewards_agreement():
    assert rrf([[(1, 9.0), (2, 5.0)], [(2, 0.9), (3, 0.8)]])[0][0] == 2


def test_api_contract_bm25():
    from fastapi.testclient import TestClient

    import api

    client = TestClient(api.app)
    r = client.post("/retrieve", json={"query": "Python programming", "filters": {"source_type": "esco"}})
    body = r.json()
    assert r.status_code == 200 and body["schema_version"] == api.SCHEMA_VERSION
    assert body["results"][0]["source_type"] == "esco" and body["results"][0]["url"].startswith("http")
    assert client.post("/retrieve", json={"query": ""}).status_code == 422  # input validated at the boundary


def test_dense_and_hybrid_plumbing(job, monkeypatch):
    """Checks Qdrant storage, filters, RRF and abstention wiring with a stand-in bag-of-words embedder.
    Says nothing about retrieval quality: real models are evaluated in evaluate.py."""
    import types
    import zlib

    import numpy as np

    class FakeST:
        def __init__(self, name):
            pass

        def encode(self, texts, normalize_embeddings=True, **_):
            def vec(t):
                v = np.zeros(1024)
                for w in t.lower().split():
                    v[zlib.crc32(w.encode()) % 1024] += 1
                return v / (np.linalg.norm(v) or 1)
            return np.array([vec(t) for t in texts]) if isinstance(texts, list) else vec(texts)

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=FakeST))
    r = Retriever(build_chunks("structure", [job], []), model="e5-small", tau=0.2)
    out = r.search("Requirements: experience with SQL and Python", mode="hybrid", filters={"doc_id": job["doc_id"]})
    assert out["status"] == "found" and out["results"][0][0]["section"] == "Requirements"
    assert r.search("zzz qqq", mode="dense")["status"] == "no_match"
