import json
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
    assert client.post("/retrieve", json={"query": ""}).status_code == 422
    empty = client.post("/retrieve", json={"query": "apprentissage automatique", "filters": {"source_type": "esco"}})
    assert empty.json()["status"] == "no_match" and empty.json()["results"] == []  # input validated at the boundary


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


def test_review_apply_never_touches_original(tmp_path, monkeypatch):
    import csv
    import hashlib

    import review

    monkeypatch.setattr(review, "REVIEWED", tmp_path / "reviewed.jsonl")
    monkeypatch.setattr(review, "DIR", tmp_path)
    before = hashlib.sha256(review.QUERIES.read_bytes()).hexdigest()
    rows = list(csv.DictReader(open(review.SHEET, encoding="utf-8-sig")))
    for r in rows:
        r["decision"] = "ACCEPT"
    e04 = next(r for r in rows if r["qid"] == "E04")
    e04["decision"], e04["corrected_gold"] = "CORRECT", e04["gold"] + " | http://data.europa.eu/esco/skill/c062bab3-3ea0-4291-9220-a2d8fef4bead"
    next(r for r in rows if r["qid"] == "N04")["decision"] = "REJECT"
    n01 = next(r for r in rows if r["qid"] == "N01")  # no-answer query corrected into an ESCO query
    n01["decision"], n01["corrected_gold"] = "CORRECT", "http://data.europa.eu/esco/skill/ae4f0cc6-e0b9-47f5-bdca-2fc2e6316dce"
    j09 = next(r for r in rows if r["qid"] == "J09")  # wording-only correction
    j09["decision"], j09["notes"] = "CORRECT", "examples only | Suggested query wording: Which frameworks are named as examples?"
    sheet = tmp_path / "sheet.csv"
    with open(sheet, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, review.COLUMNS)
        w.writeheader()
        w.writerows(rows)
    review.apply("tester", sheet)
    out = {q["qid"]: q for q in map(json.loads, open(tmp_path / "reviewed.jsonl"))}
    assert hashlib.sha256(review.QUERIES.read_bytes()).hexdigest() == before
    assert "N04" not in out and len(out) == len(rows) - 1
    assert len(out["E04"]["gold_uris"]) == 2 and len(out["E04"]["gold_original"]) == 1
    assert out["N01"]["type"] == "esco" and out["N01"]["type_original"] == "none"
    assert out["J09"]["query"] == "Which frameworks are named as examples?" and out["J09"]["gold_quotes"] == out["J09"].get("gold_quotes")
    assert "query_original" in out["J09"] and "gold_original" not in out["J09"]
    assert [json.loads(x)["qid"] for x in open(tmp_path / "rejected_queries.jsonl")] == ["N04"]

    j01 = next(r for r in rows if r["qid"] == "J01")
    j01["decision"], j01["corrected_gold"] = "CORRECT", "a quote that is not in the posting"
    with open(sheet, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, review.COLUMNS)
        w.writeheader()
        w.writerows(rows)
    with pytest.raises(SystemExit, match="J01"):
        review.apply("tester", sheet)


def test_exp02_chunkers_preserve_source(job):
    """Every exp02 chunker returns exact source offsets and covers the whole posting."""
    import numpy as np

    sys.path.insert(0, str(Path(__file__).parents[1] / "experiments/exp02_benchmark"))
    from chunkers import CHUNKERS, coverage

    rng = np.random.default_rng(0)
    enc = lambda t: (lambda v: v / np.linalg.norm(v, axis=1, keepdims=True))(rng.normal(size=(len(t), 8)))
    for name, f in CHUNKERS.items():
        chunks = f(job, enc) if name == "semantic" else f(job)
        assert coverage(job, chunks) == 1.0, name
        for c in chunks:
            body = job["text"][c["start"]:c["end"]]
            assert body.strip() and body.strip() in c["text"], name  # text is the span, or the span plus a header


def _stub_models(monkeypatch):
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

    class FakeCE:  # scores = number of query words found in the passage (deterministic)
        def __init__(self, *a, **k):
            pass

        def predict(self, pairs, **_):
            return np.array([float(sum(w in p.lower() for w in q.lower().split())) for q, p in pairs])

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=FakeST, CrossEncoder=FakeCE))


def test_parent_child_rerank_attribution_and_abstention(job, monkeypatch):
    """Children are matched, the parent section is returned with exact source offsets, the reranker reorders,
    and a calibrated threshold turns an unsupported requirement into no_match."""
    _stub_models(monkeypatch)
    sys.path.insert(0, str(Path(__file__).parents[1] / "experiments/exp02_benchmark"))
    from chunkers import parent_child_chunks

    chunks = parent_child_chunks(job)
    r = Retriever(chunks, model="e5-small", reranker="mmarco", top_n=5, thresholds={"job": 2.0})
    out = r.search("experience with SQL and Python", mode="dense", filters={"doc_id": job["doc_id"]})
    top, score = out["results"][0]
    assert out["status"] == "found" and top["section"] == "Requirements"
    assert job["text"][top["start"]:top["end"]].strip() in top["text"]  # source attribution: exact span of the posting
    assert len({c["chunk_id"] for c, _ in out["results"]}) == len(out["results"])  # parents not duplicated
    assert out["rerank_score"] == score >= 2.0
    none = r.search("Kubernetes orchestration", mode="dense", filters={"doc_id": job["doc_id"]})
    assert none["status"] == "no_match" and none["results"] == []


def test_defaults_unchanged_without_reranker_or_thresholds(job, monkeypatch):
    _stub_models(monkeypatch)
    r = Retriever(build_chunks("structure", [job], []), model="e5-small")
    out = r.search("Kubernetes orchestration", mode="dense", filters={"doc_id": job["doc_id"]})
    assert out["status"] == "found" and out["rerank_score"] is None  # no abstention unless thresholds are configured


def test_production_parent_child_equals_experiment(job):
    sys.path.insert(0, str(Path(__file__).parents[1] / "experiments/exp02_benchmark"))
    import chunkers
    import chunking

    key = lambda cs: [(c["start"], c["end"], c["text"], c["parent_start"], c["parent_end"]) for c in cs]
    assert key(chunking.parent_child_chunks(job)) == key(chunkers.parent_child_chunks(job))


def test_profiles_are_valid():
    from chunking import STRATEGIES
    from profiles import PROFILES
    from retrieval import MODELS, RERANKERS

    for name, p in PROFILES.items():
        assert p["strategy"] in STRATEGIES and p["model"] in MODELS and (p["reranker"] in RERANKERS or p["reranker"] is None), name
    assert PROFILES["baseline"]["reranker"] is None and PROFILES["baseline"]["thresholds"] is None
