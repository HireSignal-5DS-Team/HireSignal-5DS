"""LIVE end-to-end tests of the fine-tuned Matcher (real llama.cpp servers, real models). Skipped unless HS_LIVE=1 AND
both servers list their expected alias at GET /v1/models: LoRA primary (HS_MATCHER_URL, default :8081) and base
fallback (HS_FALLBACK_URL, default :8080). Run them in compute window 1 only, through scripts/live_smoke.sh.

RAG stays on (HS_RAG, default bm25, needs HIRESIGNAL_RAG_DIR). With HS_LIVE_ALLOW_NO_RAG=1 and no RAG code the tests
run with NoKnowledge and say so in the provenance; that is not the production configuration.
Nothing here asserts accuracy: 3 cases are a smoke test, not a metric."""
import json
import os
import urllib.request

import pytest

from benchmark.run import DATA, read_jsonl
from matcher.factory import build, model_provenance
from matcher.schemas import MatchReport

ENV = dict(os.environ)
PRIMARY = ENV.get("HS_MATCHER_URL", "http://127.0.0.1:8081/v1")
FALLBACK = ENV.get("HS_FALLBACK_URL", "http://127.0.0.1:8080/v1")
LORA_ALIAS, BASE_ALIAS = "Qwen/Qwen3-4B-Instruct-2507+lora", "Qwen/Qwen3-4B-Instruct-2507"
CASES = ENV.get("HS_LIVE_CASES", "val-000,val-001,val-002").split(",")


def aliases(url):
    try:
        with urllib.request.urlopen(f"{url}/models", timeout=5) as r:
            return [m["id"] for m in json.loads(r.read())["data"]]
    except Exception:  # noqa: BLE001  (any failure = server not up)
        return None


def _ready():
    if ENV.get("HS_LIVE") != "1":
        return "HS_LIVE != 1"
    p, f = aliases(PRIMARY), aliases(FALLBACK)
    if not p or LORA_ALIAS not in p:
        return f"LoRA primary not serving {LORA_ALIAS} at {PRIMARY} (got {p})"
    if not f or BASE_ALIAS not in f:
        return f"base fallback not serving {BASE_ALIAS} at {FALLBACK} (got {f})"
    return None


REASON = _ready()
pytestmark = pytest.mark.skipif(REASON is not None, reason=f"live test skipped: {REASON}")


def knowledge():
    if ENV.get("HIRESIGNAL_RAG_DIR") or ENV.get("HS_LIVE_ALLOW_NO_RAG") != "1":
        return None  # factory default: HS_RAG (bm25)
    from matcher.knowledge import NoKnowledge

    return NoKnowledge()


def case(cid):
    return next(c for c in read_jsonl(DATA / "val.jsonl") if c["case_id"] == cid)


@pytest.fixture(scope="module")
def live_out():
    env = {**ENV, "HS_JUDGE": ENV.get("HS_JUDGE", "off"), "HS_MATCHER_URL": PRIMARY, "HS_FALLBACK_URL": FALLBACK}
    p = build(env, knowledge=knowledge())
    return {cid: p.run(case(cid)["cv"], case(cid)["job"]) for cid in CASES}


def test_live_primary_answers_with_full_provenance(live_out):
    pin, _, _ = model_provenance(ENV)
    for out in live_out.values():
        rep = MatchReport.model_validate(out["match_report"])
        for x in out["requirements"]:
            p = x["provenance"]
            assert p["answered_by"] == "primary" and p["alias_verified"] is True and "MOCK" not in p
            assert p["adapter"] == pin["adapter"] and p["base_revision"] == pin["base_revision"] and p["prompt_id"] == "p1"
            assert p["knowledge_provider"] == out["knowledge"]
        assert set(rep.backend["results"]) == {r.req_id for r in rep.results}


def test_live_outputs_are_schema_valid_or_routed(live_out):
    for cid, out in live_out.items():
        text = case(cid)["cv"]["text"]
        for x in out["requirements"]:
            if x["model_decision"] is None or set(x["provenance"]["repairs"]) - {"think_block", "code_fence"}:
                assert x["requires_human_review"]  # unparseable / repaired -> review, never a silent decision
            assert all(text[a:b] == q for q, (a, b) in zip(x["evidence"], x["evidence_spans"]))
            assert x["rag_refs"] == [c["source_id"] for c in x["citations"]]


def test_live_fallback_when_primary_unreachable():
    env = {**ENV, "HS_JUDGE": "off", "HS_MATCHER_URL": "http://127.0.0.1:9/v1", "HS_FALLBACK_URL": FALLBACK,
           "HS_MAX_RETRIES": "0"}
    c = case(CASES[0])
    job = {**c["job"], "requirements": c["job"]["requirements"][:1]}
    out = build(env, knowledge=knowledge()).run(c["cv"], job)
    x = out["requirements"][0]
    assert x["provenance"]["answered_by"] == "fallback" and x["provenance"]["adapter"] is None
    assert x["provenance"]["alias_verified"] is True and "matcher:fallback_model_used" in x["review_reasons"]


def test_live_greedy_decoding_is_deterministic():
    from matcher.backends import Task
    from matcher.backends_api import OpenAICompatBackend
    from matcher.schemas import CV, Job

    c = case(CASES[0])
    cv, req = CV.model_validate(c["cv"]), Job.model_validate(c["job"]).requirements[0]
    b = OpenAICompatBackend(base_url=PRIMARY, model=LORA_ALIAS, max_retries=0)
    assert b.generate(Task(cv, req, [])) == b.generate(Task(cv, req, []))
