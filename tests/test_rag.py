"""T09 RAG: corpus / chunking, V0 parity, graph expansion, store parity, /rag/search, refs passed to /match."""
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from rag.bm25_esco import BM25EscoKnowledge
from rag.retrieval import EscoRetriever, load_concepts, terms_in_cv, text_a, text_b
from services import api
from services.matcher import matcher as matcher_mod

ROOT = Path(__file__).resolve().parents[1]
HAS_MINILM = (ROOT / "models/all-MiniLM-L6-v2/model.safetensors").exists()


@pytest.fixture(scope="module")
def minilm():
    return EscoRetriever("A", "dense", "all-MiniLM-L6-v2", device="cpu")


@pytest.fixture(scope="module")
def bm25():
    return EscoRetriever("A", "bm25")


def test_chunk_a_is_exactly_the_v2_text_the_matcher_has_seen():
    v2 = {json.loads(line)["doc_id"]: json.loads(line)["text"]
          for line in open(ROOT / "rag/data/esco/esco_ict_skills.jsonl", encoding="utf-8")}
    concepts = load_concepts()
    assert len(concepts) == len(v2) == 1621
    assert all(text_a(c) == v2[c["uri"]] for c in concepts)


def test_chunk_b_adds_broader_and_related_labels():
    c = next(c for c in load_concepts() if c["label"] == "Haskell")
    assert text_b(c).startswith(text_a(c)) and "Broader: " in text_b(c) and "computer programming" in text_b(c)


@pytest.mark.parametrize("req", [{"text": "Hands-on experience with SQL", "skill_terms": ["SQL"]},
                                 {"text": "Knowledge of the general principles of Data Warehousing"},
                                 {"text": "Good spoken English", "skill_terms": ["English"]}])
def test_bm25_chunk_a_equals_the_current_provider(bm25, req):
    old = [r["source_id"] for r in BM25EscoKnowledge().lookup(req, k=3)]
    assert [r["source_id"] for r in bm25.lookup(req, k=3)] == old


def test_refs_keep_the_format_the_lora_saw(bm25):
    refs = bm25.lookup({"text": "statistics"}, k=3)
    assert len(refs) == 3 and all(len(r["text"]) <= 300 and r["source_id"].startswith("http://data.europa.eu/esco/")
                                  for r in refs)


def test_graph_expansion_inserts_neighbours_after_the_top_hits(bm25):
    plain = bm25.ranking("Haskell", n=10)
    bm25.graph = True
    try:
        expanded = bm25.ranking("Haskell", n=10)
    finally:
        bm25.graph = False
    top = bm25.concepts[plain[0][0]]
    neighbours = {bm25.index_of[x["uri"]] for x in top["broader"] + top["related"] if x["uri"] in bm25.index_of}
    assert expanded[0] == plain[0] and neighbours and neighbours <= {i for i, _ in expanded}


def test_terms_in_cv_rule():
    assert terms_in_cv({"skill_terms": ["SQL", "Python"]}, "Python and SQL every day")
    assert not terms_in_cv({"skill_terms": ["SQL", "Spark"]}, "Python and SQL every day")
    assert not terms_in_cv({"skill_terms": []}, "anything")  # no terms: always retrieve
    assert not terms_in_cv({"skill_terms": ["C"]}, "C++ developer")  # whole word, '+' is part of the word


@pytest.mark.skipif(not HAS_MINILM, reason="MiniLM not copied to models/")
@pytest.mark.parametrize("store", ["qdrant", pytest.param("chroma", marks=pytest.mark.skipif(
    __import__("importlib").util.find_spec("chromadb") is None, reason="chromadb only installed for the T09 benchmark"))])
def test_vector_stores_give_the_numpy_ranking(tmp_path, store, minilm):
    numpy = minilm
    other = EscoRetriever("A", "dense", "all-MiniLM-L6-v2", store=store, device="cpu", store_dir=tmp_path / store)
    for q in ("PL/SQL", "neural networks and deep learning models", "Docker containers"):
        assert [i for i, _ in other.ranking(q, n=5)] == [i for i, _ in numpy.ranking(q, n=5)]
    other._client = None


def test_rag_search_endpoint_and_skip_rule(monkeypatch, bm25):
    monkeypatch.setattr(api, "_RAG", bm25)
    monkeypatch.setenv("RAG_ONLY_WHEN_MISSING", "0")
    c = TestClient(api.app)
    req = {"req_id": "r1", "text": "Hands-on experience with SQL", "skill_terms": ["SQL"]}
    body = c.post("/rag/search", json={"requirement": req, "cv_text": "SQL every day"}).json()
    assert len(body["knowledge_refs"]) == 3 and not body["skipped"]
    monkeypatch.setenv("RAG_ONLY_WHEN_MISSING", "1")
    body = c.post("/rag/search", json={"requirement": req, "cv_text": "SQL every day"}).json()
    assert body["skipped"] and body["knowledge_refs"] == []


def test_match_uses_the_refs_from_the_request(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "local")
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        reply = json.dumps({"decision": "MISSING", "basis": "not_documented", "evidence": [], "explanation": "x"})
        return httpx.Response(200, json={"choices": [{"message": {"content": reply}}]})

    ref = {"source_id": "http://data.europa.eu/esco/skill/x", "title": "SQL", "text": "SQL. A query language MARKER."}
    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = matcher_mod.match("Python dev", {"req_id": "r1", "text": "SQL", "kind": "must", "category": "skill",
                                           "skill_terms": [], "min_years": None}, client=client, refs=[ref],
                            knowledge_name="test-retriever")
    assert "MARKER" in seen[0]["messages"][1]["content"] and out["knowledge"] == "test-retriever"
    assert out["knowledge_refs"] == [{"source_id": ref["source_id"], "title": "SQL"}]
    matcher_mod.match("Python dev", {"req_id": "r1", "text": "SQL", "kind": "must", "category": "skill",
                                     "skill_terms": [], "min_years": None}, client=client, refs=[])
    assert "(none retrieved)" in seen[1]["messages"][1]["content"]
