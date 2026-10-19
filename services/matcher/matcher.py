"""Matcher station: ONE requirement x the anonymised CV -> checked decision with verified quotes.

    requirement --BM25-ESCO k=3 (knowledge, never evidence)--> prompt matcher-v1 --llama-server, LoRA scale 1,
    JSON-schema constrained (services/matcher/schema.json)--> strict parse --> validator v1 (validate.py)
"""
import json
import math
import time
from functools import lru_cache
from pathlib import Path

import httpx

from rag.bm25_esco import BM25EscoKnowledge
from services.config import env, llm_settings
from services.matcher.prompt import DECODING, load_prompt, parse_strict, user_message
from services.matcher.validate import validate

PROMPT_ID = "matcher-v1"
PROMPT_FILE = "prompts/matcher/v1.md"
SCHEMA_FILE = Path(__file__).with_name("schema.json")
# First token of each label in the Qwen3 tokenizer (llama-server /tokenize: "MET" | "MISS"+"ING" | "UNC"+"ERT"+"AIN")
LABEL_FIRST_TOKEN = {"MET": "MET", "MISSING": "MISS", "UNCERTAIN": "UNC"}
TOP_LOGPROBS = 20


def apply_confidence_rule(out, confidence, tau):
    """T07 confidence check: p(model decision) < tau -> decision UNCERTAIN (model_decision kept) + match:low_confidence.
    tau = 0.72 was chosen on the dev split of the 40 real pairs (max dev macro-F1, eval/results/2026-10-18_judge_confidence)."""
    p = ((confidence or {}).get("normalized") or {}).get(out["model_decision"]) if out["model_decision"] else None
    if p is not None and p < tau and out["decision"] != "UNCERTAIN":
        out.update(decision="UNCERTAIN", basis="ambiguous", needs_human_review=True)
        out["review_reasons"].append("match:low_confidence")
    return out


def decision_confidence(logprobs):
    """Probability of each decision label at the decision position, from llama-server's top_logprobs.

    llama-server b11139 (tools/server/README.md:579, n_probs): probabilities are a plain softmax of the logits, before
    the sampler chain, so the JSON-schema grammar does not change them. A label's probability = that of its first
    token (the three first tokens differ). `normalized` = renormalised over the three labels. None = not in the top 20.
    """
    toks = (logprobs or {}).get("content") or []
    text = ""
    for t in toks:
        if text.endswith('"decision": "'):  # the next token starts the label
            # exact pieces only: variants like ' MET' are other tokens, and the schema grammar forbids them here
            top = {x["token"]: x["logprob"] for x in t.get("top_logprobs", [])}
            raw = {lab: (round(math.exp(top[ft]), 6) if ft in top else None) for lab, ft in LABEL_FIRST_TOKEN.items()}
            total = sum(v for v in raw.values() if v)
            norm = {lab: round(v / total, 6) if v else 0.0 for lab, v in raw.items()} if total else None
            return {"label_prob": raw, "normalized": norm, "source": f"llama-server top_logprobs={TOP_LOGPROBS}, "
                    "pre-sampling softmax, first token of the label"}
        text += t["token"]
    return None


@lru_cache(maxsize=1)
def knowledge():
    return BM25EscoKnowledge()


@lru_cache(maxsize=1)
def _prompt():
    return load_prompt(PROMPT_FILE)


@lru_cache(maxsize=1)
def _schema():
    return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


def match(cv_text, req, client=None, refs=None, knowledge_name=None):
    """req: {req_id, text, kind, category, skill_terms, min_years}. Raises httpx.HTTPError if the server fails."""
    cfg = llm_settings()
    scale = None if cfg["backend"] == "cloud" else float(env("LLM_SCALE_MATCHER", "1"))
    k = int(env("MATCHER_K", "3"))
    # refs from the request (T09: n8n node "RAG lookup" -> /match); [] = no knowledge block; None = built-in BM25
    if refs is None:
        refs, knowledge_name = knowledge().lookup(req, k=k), f"{knowledge().name} k={k}"
    else:
        refs, knowledge_name = refs[:k], knowledge_name or "refs from the request"
    system, template = _prompt()
    # max_tokens: V2's 192 cut long multi-quote replies (finish_reason "length" -> invalid JSON, T04 smoke). With greedy
    # decoding a higher limit leaves every reply that finished within 192 tokens unchanged.
    decoding = DECODING | {"max_tokens": int(env("MATCHER_MAX_TOKENS", "384"))}
    body = {"model": cfg["model"], "cache_prompt": False, **decoding,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user_message(template, cv_text, req, refs)}],
            # llama-server b11139 tools/server/README.md:1316: the schema is compiled to a grammar
            "response_format": {"type": "json_object", "schema": _schema()},
            "logprobs": True, "top_logprobs": TOP_LOGPROBS}  # confidence for the Outcome gate (T06); output unchanged
    if scale is not None:
        body["lora"] = [{"id": 0, "scale": scale}]
    headers = {"Authorization": f"Bearer {cfg['api_key']}"} if cfg["api_key"] else {}
    client = client or httpx.Client(timeout=cfg["timeout"])
    t = time.perf_counter()
    r = client.post(cfg["base_url"].rstrip("/") + "/chat/completions", json=body, headers=headers)
    r.raise_for_status()
    choice = r.json()["choices"][0]
    raw, finish = choice["message"]["content"], choice.get("finish_reason")
    latency = round(time.perf_counter() - t, 3)
    out = validate(parse_strict(raw), cv_text, req)
    if finish == "length":
        out["review_reasons"].append("model_output_truncated")
        out["needs_human_review"] = True
    confidence = decision_confidence(choice.get("logprobs"))
    apply_confidence_rule(out, confidence, float(env("MATCHER_TAU_CONF", "0.72")))
    return {"req_id": req["req_id"], **out,
            "knowledge_refs": [{"source_id": x["source_id"], "title": x["title"]} for x in refs],
            "model": {"name": cfg["model"], "backend": cfg["backend"], "lora_scale": scale, "latency_s": latency,
                      "finish_reason": finish, "max_tokens": decoding["max_tokens"]},
            "confidence": confidence,
            "prompt_id": PROMPT_ID, "schema": "services/matcher/schema.json", "knowledge": knowledge_name}
