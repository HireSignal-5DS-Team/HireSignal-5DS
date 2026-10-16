"""Build the HireSignal pipeline from environment configuration (config/matcher.env.example).

Matcher : HS_MATCHER_URL / HS_MATCHER_MODEL   primary   (default: fine-tuned LoRA server, :8081)
          HS_FALLBACK_URL / HS_FALLBACK_MODEL fallback  (default: original Qwen3-4B server, :8080); HS_FALLBACK=off disables
          Pinned provenance (model, base revision, GGUF weights, adapter repo + sha) from config/matcher_models.json
          (HS_MODELS_CONFIG); HS_LORA_REPO / HS_LORA_SHA override the adapter actually served on the primary.
          HS_TIMEOUT (s, default 300), HS_MAX_RETRIES (default 2) per endpoint before falling back.
Decoding: HS_JSON_SCHEMA = off (default) | fallback | all: constrain the named endpoint(s) to the ModelAnswer JSON
          schema (llama.cpp grammar). Recorded in provenance; measure on val before enabling.
RAG     : HS_RAG = none | bm25 | qdrant | gated | gated-qdrant (default gated = S1's rag.gated.v1 over BM25: on the LIVE
          LoRA val run it matches no-RAG macro-F1 within noise and keeps BM25's alias gain without its false-MET rise,
          see rag_opt/results/e2e/e2e_report.md; qdrant = team dense index under HIRESIGNAL_RAG_DIR/index)
Judge   : HS_JUDGE_MODEL (Hub id or local dir; HS_JUDGE_DIR is the old name) + HS_JUDGE_REVISION (Hub commit sha),
          HS_JUDGE_TAU_PASS / HS_JUDGE_TAU_FAIL (HS_JUDGE_TAU sets both), HS_JUDGE_HYPOTHESIS (v1 | v2).
          Defaults: JUDGE_DEFAULT pinned in JUDGE_MODELS, thresholds calibrated on train-dev (docs/JUDGE.md). A local
          dir may carry judge_calibration.json; a missing local dir falls back to JUDGE_DEFAULT. HS_JUDGE=off disables
Bias    : HS_BIAS_AUDITOR = rules_v1 (default, matcher.bias_audit) | rules_v2 | rules_v2+reviewer (S4, bias/auditor.py).
          The reviewer is opt-in (one extra LLM call per result) and runs on the BASE model only:
          HS_BIAS_REVIEWER_URL (default HS_FALLBACK_URL) / HS_BIAS_REVIEWER_MODEL (default the base alias); never the LoRA.
          HS_LIVE_COUNTERFACTUAL=1 adds the inline counterfactual test (8 extra Matcher calls/requirement)
"""
import json
import os
from collections import namedtuple
from pathlib import Path

from .backends_api import MODELS_CONFIG, FallbackBackend, OpenAICompatBackend, pinned_provenance  # noqa: F401
from .knowledge import NoKnowledge, QdrantKnowledge, RagKnowledge
from .pipeline import Pipeline
from .schemas import ModelAnswer

# Pinned Hub NLI checkpoints and their train-dev calibration (S7, judge/experiment.py, docs/JUDGE.md §4).
JUDGE_MODELS = {
    "cross-encoder/nli-deberta-v3-xsmall": {"revision": "a150876415327c80daeff35ca6f68f5ed8cf5c24", "licence": "apache-2.0",
                                            "tau_pass": 0.75, "tau_fail": 0.85, "hypothesis": "v2"},
    "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli": {"revision": "6f5cf0a2b59cabb106aca4c287eed12e357e90eb",
                                                     "licence": "mit", "tau_pass": 0.4, "tau_fail": 0.65, "hypothesis": "v1"},
}
JUDGE_DEFAULT = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"
PRETRAINED_JUDGE = (JUDGE_DEFAULT, JUDGE_MODELS[JUDGE_DEFAULT]["tau_fail"])
FINETUNED_JUDGE = ("/home/user/judge_runs/deberta-hs-v1/best", 0.85)  # never published; used only if present
JudgeConfig = namedtuple("JudgeConfig", "model tau_pass name revision tau_fail hypothesis")


def model_provenance(env):
    """(primary, fallback, cfg) provenance dicts for OpenAICompatBackend, from the pinned config + env overrides."""
    return pinned_provenance(env)


def _knowledge_attr(name):
    """S1 providers (rag.gated.v1) live in matcher/knowledge.py on S1's branch; fail loudly until merged."""
    from . import knowledge as k

    if not hasattr(k, name):
        raise ImportError(f"matcher.knowledge.{name} not available: S1 (session/s1-rag-optimization) not merged")
    return getattr(k, name)


def _gated_qdrant(env):
    """S1's gated provider over Qdrant e5-small candidates, built as rag_opt/run_arm.py:provider_factory does
    (calibrated ESCO cosine threshold of exp03). Needs sentence-transformers and the persisted index."""
    import sys

    gated = _knowledge_attr("GatedKnowledge")
    rag = Path(env.get("HIRESIGNAL_RAG_DIR") or Path(__file__).resolve().parents[1] / "rag")
    if str(rag) not in sys.path:
        sys.path.insert(0, str(rag))
    from corpus import build_chunks
    from retrieval import Retriever

    tau = json.loads((rag / "experiments/exp03_optimization/thresholds.json").read_text())["structure@300 | e5-small"]["esco"]
    r = Retriever(build_chunks("structure"), model="e5-small", store_path=rag / "index")
    return gated(retriever=r, mode="dense", dense_tau=tau)


BIAS_AUDITOR_DEFAULT = "rules_v2"  # blind holdout (n=44): same recall as v1 (19/26), FPR 1/18 vs 9/18; no model call


def bias_auditor(env, cfg):
    """None for rules_v1 (matcher.bias_audit), else S4's BiasAuditor. Fails loudly if bias/ is missing."""
    variant = env.get("HS_BIAS_AUDITOR", BIAS_AUDITOR_DEFAULT)
    if variant == "rules_v1":
        return None
    from bias.auditor import BiasAuditor  # S4 package; ImportError here = S4 not merged on this branch

    reviewer = None
    if "reviewer" in variant:
        from bias.reviewer import LLMReviewer

        url = env.get("HS_BIAS_REVIEWER_URL") or env.get("HS_FALLBACK_URL", cfg["fallback"]["url"])
        model = env.get("HS_BIAS_REVIEWER_MODEL", cfg["fallback"]["served_alias"])
        if model == cfg["primary"]["served_alias"] or url == env.get("HS_MATCHER_URL", cfg["primary"]["url"]):
            raise ValueError("the bias reviewer must not run on the Matcher LoRA endpoint (measured on the base model only)")
        reviewer = LLMReviewer(OpenAICompatBackend(base_url=url, model=model, timeout=float(env.get("HS_TIMEOUT", 300)),
                                                   max_tokens=160, label="bias-reviewer"))
    return BiasAuditor(variant, reviewer=reviewer)


def judge_config(env):
    """JudgeConfig(model, tau_pass, name, revision, tau_fail, hypothesis) from env, or None when HS_JUDGE=off."""
    if env.get("HS_JUDGE", "on") == "off":
        return None
    model = env.get("HS_JUDGE_MODEL") or env.get("HS_JUDGE_DIR")
    note = ""
    if model is None and Path(FINETUNED_JUDGE[0]).exists():  # legacy fine-tuned base checkpoint (tau 0.85)
        model, known = FINETUNED_JUDGE[0], {"tau_pass": FINETUNED_JUDGE[1], "tau_fail": FINETUNED_JUDGE[1], "hypothesis": "v1"}
    else:
        model = model or JUDGE_DEFAULT
        if model.startswith("/") and not Path(model).exists():
            note, model = f" (checkpoint {model} missing)", JUDGE_DEFAULT
        known = JUDGE_MODELS.get(model)
        if known is None and (Path(model) / "judge_calibration.json").exists():
            known = json.loads((Path(model) / "judge_calibration.json").read_text())
        known = known or {}
    tau = env.get("HS_JUDGE_TAU")
    tau_pass = float(env.get("HS_JUDGE_TAU_PASS") or tau or known.get("tau_pass", 0.5))
    tau_fail = float(env.get("HS_JUDGE_TAU_FAIL") or tau or known.get("tau_fail", 0.5))
    hyp = env.get("HS_JUDGE_HYPOTHESIS") or known.get("hypothesis", "v1")
    from .judge import HYPOTHESES

    if hyp not in HYPOTHESES:
        raise ValueError(f"HS_JUDGE_HYPOTHESIS must be one of {sorted(HYPOTHESES)}, not {hyp!r}")
    calibrated = "" if known or tau or env.get("HS_JUDGE_TAU_PASS") else " (uncalibrated thresholds)"
    name = ("nli-judge-finetuned" if model == FINETUNED_JUDGE[0] else f"nli-judge:{model}") + note + calibrated
    return JudgeConfig(model, tau_pass, name, env.get("HS_JUDGE_REVISION") or known.get("revision"), tau_fail, hyp)


def build(env=None, knowledge=None, judge=None):
    env = dict(os.environ if env is None else env)
    prov_p, prov_f, cfg = model_provenance(env)
    js = env.get("HS_JSON_SCHEMA", "off")
    if js not in ("off", "fallback", "all"):
        raise ValueError(f"HS_JSON_SCHEMA must be off | fallback | all, not {js!r}")
    schema = ModelAnswer.model_json_schema()
    primary = OpenAICompatBackend(base_url=env.get("HS_MATCHER_URL", cfg["primary"]["url"]),
                                  model=env.get("HS_MATCHER_MODEL", cfg["primary"]["served_alias"]),
                                  timeout=float(env.get("HS_TIMEOUT", 300)), max_retries=int(env.get("HS_MAX_RETRIES", 2)),
                                  label="matcher-lora", provenance=prov_p,
                                  response_schema=schema if js == "all" else None)
    backend = primary
    if env.get("HS_FALLBACK", "on") != "off":
        backend = FallbackBackend(primary, OpenAICompatBackend(
            base_url=env.get("HS_FALLBACK_URL", cfg["fallback"]["url"]),
            model=env.get("HS_FALLBACK_MODEL", cfg["fallback"]["served_alias"]), timeout=float(env.get("HS_TIMEOUT", 300)),
            max_retries=int(env.get("HS_MAX_RETRIES", 2)), label="matcher-base-fallback", provenance=prov_f,
            response_schema=schema if js in ("fallback", "all") else None))
    if knowledge is None:
        rag = env.get("HS_RAG", "gated")
        providers = {"none": NoKnowledge, "bm25": RagKnowledge, "qdrant": QdrantKnowledge,
                     "gated": lambda: _knowledge_attr("GatedKnowledge")(),
                     "gated-qdrant": lambda: _gated_qdrant(env)}
        if rag not in providers:
            raise ValueError(f"HS_RAG must be one of {sorted(providers)}, not {rag!r}")
        knowledge = providers[rag]()
    if judge is None and (jcfg := judge_config(env)):
        from .judge import NLIJudge

        judge = NLIJudge(jcfg.model, tau_pass=jcfg.tau_pass, tau_fail=jcfg.tau_fail, name=jcfg.name,
                         revision=jcfg.revision, hypothesis_template=jcfg.hypothesis)
    return Pipeline(backend, knowledge, judge=judge, live_counterfactual=env.get("HS_LIVE_COUNTERFACTUAL") == "1",
                    auditor=bias_auditor(env, cfg))
