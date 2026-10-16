"""Build the HireSignal pipeline from environment configuration (config/matcher.env.example).

Matcher : HS_MATCHER_URL / HS_MATCHER_MODEL   primary   (default: fine-tuned LoRA server, :8081)
          HS_FALLBACK_URL / HS_FALLBACK_MODEL fallback  (default: original Qwen3-4B server, :8080); HS_FALLBACK=off disables
          Pinned provenance (model, base revision, GGUF weights, adapter repo + sha) from config/matcher_models.json
          (HS_MODELS_CONFIG); HS_LORA_REPO / HS_LORA_SHA override the adapter actually served on the primary.
RAG     : HS_RAG = none | bm25 | qdrant (default bm25: the measured best ESCO provider is still "none" or "bm25", see
          docs; qdrant = team dense index, persisted under HIRESIGNAL_RAG_DIR/index)
Judge   : HS_JUDGE_DIR (fine-tuned DeBERTa; if missing, the pretrained MoritzLaurer model) and HS_JUDGE_TAU
          (calibrated on train-dev: 0.85 fine-tuned, 0.65 pretrained); HS_JUDGE=off disables
Bias    : rules always; HS_LIVE_COUNTERFACTUAL=1 adds the inline counterfactual test (8 extra Matcher calls/requirement)
"""
import json
import os
from pathlib import Path

from .backends_api import FallbackBackend, OpenAICompatBackend
from .knowledge import NoKnowledge, QdrantKnowledge, RagKnowledge
from .pipeline import Pipeline

PRETRAINED_JUDGE = ("MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli", 0.65)
FINETUNED_JUDGE = ("/home/user/judge_runs/deberta-hs-v1/best", 0.85)
MODELS_CONFIG = Path(__file__).resolve().parents[1] / "config" / "matcher_models.json"


def model_provenance(env):
    """(primary, fallback) provenance dicts for OpenAICompatBackend, from the pinned config + env overrides."""
    cfg = json.loads(Path(env.get("HS_MODELS_CONFIG") or MODELS_CONFIG).read_text())
    base = {k: cfg["base"][k] for k in ("model_id", "base_revision", "weights", "runtime")}
    primary = {**base, "role": "primary", "adapter": dict(cfg["primary"]["adapter"])}
    if env.get("HS_LORA_REPO") or env.get("HS_LORA_SHA"):
        primary["adapter"] = {"repo": env.get("HS_LORA_REPO", primary["adapter"]["repo"]), "sha": env.get("HS_LORA_SHA")}
    return primary, {**base, "role": "fallback", "adapter": None}, cfg


def judge_config(env):
    if env.get("HS_JUDGE", "on") == "off":
        return None
    d = env.get("HS_JUDGE_DIR") or FINETUNED_JUDGE[0]
    if Path(d).exists() or not d.startswith("/"):
        tau = float(env.get("HS_JUDGE_TAU") or (FINETUNED_JUDGE[1] if d == FINETUNED_JUDGE[0] else PRETRAINED_JUDGE[1]))
        return d, tau, "nli-judge-finetuned" if d == FINETUNED_JUDGE[0] else "nli-judge"
    return PRETRAINED_JUDGE[0], PRETRAINED_JUDGE[1], "nli-judge-pretrained (fine-tuned checkpoint missing)"


def build(env=None, knowledge=None, judge=None):
    env = dict(os.environ if env is None else env)
    prov_p, prov_f, cfg = model_provenance(env)
    primary = OpenAICompatBackend(base_url=env.get("HS_MATCHER_URL", cfg["primary"]["url"]),
                                  model=env.get("HS_MATCHER_MODEL", cfg["primary"]["served_alias"]),
                                  timeout=float(env.get("HS_TIMEOUT", 300)), label="matcher-lora", provenance=prov_p)
    backend = primary
    if env.get("HS_FALLBACK", "on") != "off":
        backend = FallbackBackend(primary, OpenAICompatBackend(
            base_url=env.get("HS_FALLBACK_URL", cfg["fallback"]["url"]),
            model=env.get("HS_FALLBACK_MODEL", cfg["fallback"]["served_alias"]), timeout=float(env.get("HS_TIMEOUT", 300)),
            label="matcher-base-fallback", provenance=prov_f))
    if knowledge is None:
        rag = env.get("HS_RAG", "bm25")
        knowledge = {"none": NoKnowledge, "bm25": RagKnowledge, "qdrant": QdrantKnowledge}[rag]()
    if judge is None and (jcfg := judge_config(env)):
        from .judge import NLIJudge

        judge = NLIJudge(jcfg[0], tau_pass=jcfg[1], tau_fail=jcfg[1], name=jcfg[2])
    return Pipeline(backend, knowledge, judge=judge, live_counterfactual=env.get("HS_LIVE_COUNTERFACTUAL") == "1")
