"""LLM fairness reviewer for one validated Matcher result (Bias Auditor variant "reviewer").

The reviewer reads the requirement, the decision, the evidence quotes and the explanation (never the full CV) and
returns {flag, category, attributes, rationale}. It is served OpenAI-compatible (llama.cpp), by default the same
original Qwen3-4B-Instruct-2507 Q4_K_M server as the Matcher fallback (:8080), so it needs no extra model in memory.

A transport failure or an unparseable reply is recorded as an error and never turned into a verdict: the auditor
then keeps the rules verdict (bias/auditor.py) and the evaluation counts the error.

Adapter hook: `AdapterReviewer` only accepts an adapter listed as approved in bias/adapters.json for this exact base
and revision. No adapter has passed vetting (docs/BIAS_AUDITOR.md), so the approved list is empty.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
PROMPT_ID = "reviewer_v1"
BASE_MODEL = "Qwen/Qwen3-4B-Instruct-2507"
CATEGORIES = {"none", "explanation_leak", "unsupported_judgment", "demographic_evidence"}


def system_prompt(prompt_id=PROMPT_ID):
    return (HERE / "prompts" / f"{prompt_id}.txt").read_text()


def user_message(result, requirement_text):
    return (f"Requirement: {requirement_text}\nDecision: {result.decision} ({result.basis})\n"
            f"Evidence: {json.dumps(list(result.evidence), ensure_ascii=False)}\nExplanation: {result.explanation}\n")


def messages(result, requirement_text, prompt_id=PROMPT_ID):
    return [{"role": "system", "content": system_prompt(prompt_id)},
            {"role": "user", "content": user_message(result, requirement_text)}]


def parse(raw):
    """First JSON object with a boolean `flag`; None if there is none (never guessed from free text)."""
    raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S)
    start = raw.find("{")
    while start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(raw[start:])
            if isinstance(obj, dict) and isinstance(obj.get("flag"), bool):
                cat = obj.get("category") if obj.get("category") in CATEGORIES else ("none" if not obj["flag"] else "unspecified")
                attrs = obj.get("attributes") if isinstance(obj.get("attributes"), list) else []
                return {"flag": obj["flag"], "category": cat, "attributes": [str(a) for a in attrs][:6],
                        "rationale": str(obj.get("rationale", ""))[:300]}
        except json.JSONDecodeError:
            pass
        start = raw.find("{", start + 1)
    return None


class LLMReviewer:
    """client: anything with chat(messages, max_tokens) -> str, last_call dict and info() (OpenAICompatBackend)."""

    def __init__(self, client, prompt_id=PROMPT_ID, max_tokens=160):
        self.client, self.prompt_id, self.max_tokens = client, prompt_id, max_tokens

    def info(self):
        return {"reviewer": "llm", "prompt_id": self.prompt_id, "max_tokens": self.max_tokens, "client": self.client.info()}

    def review(self, result, requirement_text):
        raw = self.client.chat(messages(result, requirement_text, self.prompt_id), max_tokens=self.max_tokens)
        call = dict(getattr(self.client, "last_call", {}) or {})
        verdict = None if call.get("error") else parse(raw)
        err = call.get("error") or (None if verdict else "reviewer_output_invalid")
        return {"verdict": verdict, "error": err, "latency_s": call.get("latency_s"), "raw": (raw or "")[:400],
                "prompt_tokens": call.get("prompt_tokens"), "completion_tokens": call.get("completion_tokens")}


def load_registry(path=HERE / "adapters.json"):
    return json.loads(Path(path).read_text())


class AdapterReviewer(LLMReviewer):
    """Reviewer served with a LoRA adapter (llama.cpp `--lora`). Refuses any adapter that is not approved in the
    vetting registry for this base model and revision; the adapter's repo and sha are recorded in info()."""

    def __init__(self, client, adapter_repo, adapter_sha, registry=None, **kw):
        reg = registry if registry is not None else load_registry()
        ok = [a for a in reg.get("approved", []) if a.get("repo") == adapter_repo and a.get("sha") == adapter_sha
              and a.get("base_model") == BASE_MODEL]
        if not ok:
            raise ValueError(f"adapter {adapter_repo}@{adapter_sha} is not approved for {BASE_MODEL} in bias/adapters.json")
        super().__init__(client, **kw)
        self.adapter = ok[0]

    def info(self):
        return {**super().info(), "adapter_repo": self.adapter["repo"], "adapter_sha": self.adapter["sha"]}
