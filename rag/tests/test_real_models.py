"""Real-model regression, attribution, no-answer and performance tests (opt-in: RAG_REAL=1, needs model download).

    RAG_REAL=1 HF_HOME=<cache> CUDA_VISIBLE_DEVICES= python -m pytest -q rag/tests/test_real_models.py
"""
import os
import sys
import time
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
pytestmark = pytest.mark.skipif(os.environ.get("RAG_REAL") != "1", reason="set RAG_REAL=1 to run real-model tests")

from corpus import build_chunks, load_jobs  # noqa: E402
from evaluate import is_hit, load_queries  # noqa: E402
from profiles import PROFILES  # noqa: E402
from retrieval import Retriever  # noqa: E402

DEV = Path(__file__).parents[1] / "eval/queries_reviewed.jsonl"


@pytest.fixture(scope="module")
def baseline():
    p = PROFILES["baseline"]
    return Retriever(build_chunks(p["strategy"]), model=p["model"])


def _filters(q):
    return {"doc_id": q["job_id"]} if q["type"] == "job" else {"source_type": "esco"}


def test_regression_dev_matcher_hit_at_1(baseline):
    """exp03 measured 31/40 Hit@1 on ESCO + job-filtered dev queries for this configuration."""
    qs = [q for q in load_queries(load_jobs(), DEV) if q["type"] != "none"]
    hits = sum(bool(out["results"]) and is_hit(q, out["results"][0][0])
               for q in qs for out in [baseline.search(q["query"], k=10, mode="dense", filters=_filters(q))])
    assert hits >= 31, hits


def test_source_attribution(baseline):
    jobs = {j["doc_id"]: j for j in load_jobs()}
    for q in [q for q in load_queries(load_jobs(), DEV) if q["type"] == "job"][:10]:
        for c, _ in baseline.search(q["query"], k=5, mode="dense", filters=_filters(q))["results"]:
            assert c["doc_id"] == q["job_id"]  # job filter is enforced
            assert jobs[c["doc_id"]]["text"][c["start"]:c["end"]].strip() in c["text"]  # exact source span
            assert c["url"].startswith("https://www.usajobs.gov/job/")


def test_no_answer_with_abstention_profile():
    p = PROFILES["baseline-abstain-experimental"]
    r = Retriever(build_chunks(p["strategy"]), model=p["model"], thresholds=p["thresholds"])
    assert r.search("beekeeping", mode="dense", filters={"source_type": "esco"})["status"] == "no_match"


def test_performance_p95_realtime_budget(baseline):
    qs = [q for q in load_queries(load_jobs(), DEV) if q["type"] != "none"][:20]
    for q in qs:  # warm-up
        baseline.search(q["query"], mode="dense", filters=_filters(q))
    ms = []
    for _ in range(3):
        for q in qs:
            t = time.perf_counter()
            baseline.search(q["query"], mode="dense", filters=_filters(q))
            ms.append((time.perf_counter() - t) * 1000)
    assert np.percentile(ms, 95) <= 300, np.percentile(ms, 95)


@pytest.mark.parametrize("name", list(PROFILES))
def test_every_profile_serves_from_persisted_index(name):
    """Each profile loads from rag/index (built once by build_index.py), answers a job-filtered query with an exact
    source span from the right posting, and keeps the experimental features off unless the profile enables them."""
    p = PROFILES[name]
    r = Retriever(build_chunks(p["strategy"]), model=p["model"], store_path=Path(__file__).parents[1] / "index",
                  reranker=p["reranker"], top_n=p["top_n"] or 10, thresholds=p["thresholds"])
    try:
        jobs = {j["doc_id"]: j["text"] for j in load_jobs()}
        out = r.search("experience with Python", k=3, mode="dense", filters={"doc_id": "usajobs-884225200"})
        assert out["status"] == "found"
        for c, _ in out["results"]:
            assert c["doc_id"] == "usajobs-884225200" and jobs[c["doc_id"]][c["start"]:c["end"]].strip() in c["text"]
        assert (out["rerank_score"] is not None) == bool(p["reranker"])
    finally:
        r.close()
