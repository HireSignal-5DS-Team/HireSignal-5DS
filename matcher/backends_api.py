"""OpenAI-compatible chat backend for the Matcher (Qwen3-4B-Instruct-2507).

One code path serves:
- local inference: llama.cpp server (`python -m llama_cpp.server --model <gguf>`), vLLM, Ollama (`/v1`), or
- a hosted API (any OpenAI-compatible /v1/chat/completions endpoint).

Configuration (constructor args or environment): base_url (HS_LLM_BASE_URL), model (HS_LLM_MODEL),
api key read from the env var named by api_key_env (default HS_LLM_API_KEY; never stored or logged).
Greedy decoding (temperature 0), bounded retries with exponential backoff, per-call timeout.
After each call `last_call` holds {latency_s, prompt_tokens, completion_tokens, error, attempts}.
On final failure generate() returns "" so the validator records `model_output_invalid` (no fabricated decision).

Provenance: `provenance` (from config/matcher_models.json via matcher/factory.py) names the model, base revision,
weights and adapter (repo + sha, or None). llama-cpp-python's server answers ANY requested alias with its default
model and echoes the requested name in the response, so the response's `model` field proves nothing. The served
alias is therefore checked against GET /v1/models (`verify_alias`): True, False (another model is served there) or
None (not checked / endpoint unreachable).
"""
import json
import os
import time
from pathlib import Path
import urllib.error
import urllib.request

from . import prompt

MODELS_CONFIG = Path(__file__).resolve().parents[1] / "config" / "matcher_models.json"


def pinned_provenance(env=None, path=None):
    """(primary, fallback, cfg) provenance from config/matcher_models.json; HS_LORA_REPO / HS_LORA_SHA override."""
    env = os.environ if env is None else env
    cfg = json.loads(Path(path or env.get("HS_MODELS_CONFIG") or MODELS_CONFIG).read_text())
    base = {k: cfg["base"][k] for k in ("model_id", "base_revision", "weights", "runtime")}
    primary = {**base, "role": "primary", "adapter": dict(cfg["primary"]["adapter"])}
    if env.get("HS_LORA_REPO") or env.get("HS_LORA_SHA"):
        primary["adapter"] = {"repo": env.get("HS_LORA_REPO", primary["adapter"]["repo"]), "sha": env.get("HS_LORA_SHA")}
    return primary, {**base, "role": "fallback", "adapter": None}, cfg


def default_provenance(model, provider):
    """For a backend built without provenance (e.g. benchmark.run): a LOCAL endpoint whose alias is one of the pinned
    aliases gets that pin; anything else (hosted ids, other models) gets none rather than a guess."""
    if provider != "local":
        return {}
    try:
        p, f, cfg = pinned_provenance()
    except (OSError, ValueError, KeyError):
        return {}
    return {cfg["primary"]["served_alias"]: p, cfg["fallback"]["served_alias"]: f}.get(model, {})


class OpenAICompatBackend:
    def __init__(self, base_url=None, model=None, api_key_env="HS_LLM_API_KEY", timeout=120.0, max_retries=2,
                 max_tokens=192, label=None, price_per_mtok=None, provider="local", provenance=None, response_schema=None):
        self.base_url = (base_url or os.environ.get("HS_LLM_BASE_URL", "http://127.0.0.1:8080/v1")).rstrip("/")
        self.model = model or os.environ.get("HS_LLM_MODEL", "Qwen/Qwen3-4B-Instruct-2507")
        self.api_key_env, self.timeout, self.max_retries, self.max_tokens = api_key_env, timeout, max_retries, max_tokens
        self.label, self.provider = label or self.model, provider
        self.price_per_mtok = price_per_mtok  # (input, output) USD per 1M tokens, only for cost estimates
        self.last_call, self.totals = {}, {"calls": 0, "errors": 0, "prompt_tokens": 0, "completion_tokens": 0}
        self.provenance_cfg = dict(provenance if provenance is not None else default_provenance(self.model, provider))
        # Constrained decoding (S1 request s1-template-echo-json): llama-cpp-python 0.3.16 compiles
        # response_format {"type": "json_object", "schema": ...} to a grammar, so decision/basis can only take a valid
        # label. The label is still the model's choice, but the "unparseable -> UNCERTAIN" path disappears: off by
        # default, recorded in provenance, to be measured on val before use.
        self.response_schema = response_schema
        self._served, self._checks = None, 0  # cached result of verify_alias(): (verified, served_aliases)

    def info(self):
        return {"backend": "openai_compat", "is_model": True, "model_id": self.model, "label": self.label,
                "provider": self.provider, "base_url": self.base_url if self.provider == "local" else "<hosted>",
                "decoding": {"temperature": 0, "max_tokens": self.max_tokens}, "timeout_s": self.timeout,
                "max_retries": self.max_retries, "prompt_version": prompt.PROMPT_VERSION,
                "adapter_id": (self.provenance_cfg.get("adapter") or {}).get("repo"),
                "adapter_revision": (self.provenance_cfg.get("adapter") or {}).get("sha"),
                "revision": os.environ.get("HS_LLM_REVISION"), "base_revision": self.provenance_cfg.get("base_revision"),
                "provenance": self.provenance()}

    def verify_alias(self, refresh=False):
        """Is `self.model` among the aliases the server lists at GET /v1/models? Cached; refresh=True re-checks."""
        if self._served is None or refresh:
            try:
                req = urllib.request.Request(f"{self.base_url}/models", headers=self._headers())
                with urllib.request.urlopen(req, timeout=min(self.timeout, 10)) as r:
                    ids = [m.get("id") for m in json.loads(r.read()).get("data", [])]
                self._served = (self.model in ids, ids)
            except (urllib.error.URLError, TimeoutError, OSError, ValueError, AttributeError) as e:
                self._served = (None, f"unreachable: {type(e).__name__}")
        return self._served

    def provenance(self):
        """Who answers through this endpoint. Static fields come from config; alias_verified from /v1/models."""
        c = self.provenance_cfg
        verified, served = self._served or (None, None)
        return {"role": c.get("role"), "model_id": c.get("model_id", self.model), "served_alias": self.model,
                "base_revision": c.get("base_revision"), "weights": c.get("weights"), "adapter": c.get("adapter"),
                "runtime": c.get("runtime"), "endpoint": self.base_url if self.provider == "local" else "<hosted>",
                "alias_verified": verified, "served_aliases": served, "prompt_id": prompt.PROMPT_VERSION,
                "constrained_decoding": self._schema_id()}

    def _schema_id(self):
        if not self.response_schema:
            return None
        import hashlib
        h = hashlib.sha256(json.dumps(self.response_schema, sort_keys=True).encode()).hexdigest()[:12]
        return f"json_schema:{self.response_schema.get('title', 'schema')}@{h}"

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(self.api_key_env)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def _post(self, payload):
        req = urllib.request.Request(f"{self.base_url}/chat/completions", data=json.dumps(payload).encode(),
                                     headers=self._headers())
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())

    def chat(self, messages, max_tokens=None):
        payload = {"model": self.model, "messages": messages, "temperature": 0, "top_p": 1,
                   "max_tokens": max_tokens or self.max_tokens, "seed": 0}
        if self.response_schema:
            payload["response_format"] = {"type": "json_object", "schema": self.response_schema}
        t0, err = time.perf_counter(), None
        for attempt in range(1, self.max_retries + 2):
            try:
                out = self._post(payload)
                choice = out["choices"][0]
                content = choice["message"]["content"]
                if content is not None and not isinstance(content, str):  # QA-015: e.g. a list; not a model answer
                    raise TypeError(f"content is {type(content).__name__}, not text")
                self._record(t0, attempt, None, out.get("usage") or {}, choice.get("finish_reason"))
                return content or ""
            except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, TypeError, AttributeError,
                    ValueError) as e:  # ValueError covers JSONDecodeError; Type/Attribute: malformed body (QA-015)
                err = f"{type(e).__name__}: {str(e)[:200]}"
                if isinstance(e, urllib.error.HTTPError) and e.code in (400, 401, 403, 404):
                    break  # not retryable
                if attempt <= self.max_retries:
                    time.sleep(min(2 ** attempt, 20))
        self._record(t0, attempt, err, {})
        return ""

    def _record(self, t0, attempt, err, usage, finish_reason=None):
        self.last_call = {"latency_s": round(time.perf_counter() - t0, 3), "attempts": attempt, "error": err,
                          "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
                          "finish_reason": finish_reason}
        t = self.totals
        t["calls"] += 1
        t["errors"] += err is not None
        t["prompt_tokens"] += usage.get("prompt_tokens") or 0
        t["completion_tokens"] += usage.get("completion_tokens") or 0

    def generate(self, task):
        if self.provider == "local" and (self._served is None or (self._served[0] is None and self._checks < 3)):
            self._checks += 1  # checked once; re-checked (max 3 times) while /v1/models was unreachable
            self.verify_alias(refresh=True)
        raw = self.chat(task.messages)
        self.last_call["provenance"] = self.provenance()
        return raw


class FallbackBackend:
    """Primary Matcher model with a fallback (e.g. fine-tuned LoRA endpoint -> original Qwen3-4B endpoint).
    Falls back ONLY on a transport failure of the primary (error after its retries), never on a model answer the
    validator dislikes. `last_call["used"]` records which model produced each answer and `last_call["provenance"]`
    that model's provenance, so every result cites the model that actually answered."""

    def __init__(self, primary, fallback):
        self.primary, self.fallback = primary, fallback
        self.last_call = {}

    def info(self):
        return {"backend": "fallback", "is_model": True, "primary": self.primary.info(), "fallback": self.fallback.info(),
                "model_id": self.primary.info().get("model_id"), "prompt_version": prompt.PROMPT_VERSION}

    @staticmethod
    def _prov(b, role):
        if hasattr(b, "provenance"):
            return {**b.provenance(), "role": role}
        info = b.info() if hasattr(b, "info") else {}  # not an HTTP model endpoint (scripted / baseline backend)
        return {"model_id": getattr(b, "model", None) or info.get("model_id"), "adapter": None, "role": role,
                "MOCK": not info.get("is_model", False)}

    @staticmethod
    def _call(b, task):
        """b.generate(task); an exception is a transport failure recorded in last_call, never a crash (QA-015)."""
        try:
            return b.generate(task)
        except Exception as e:  # noqa: BLE001  (any backend bug must route to fallback/review, not abort the run)
            b.last_call = {**(getattr(b, "last_call", None) or {}), "error": f"{type(e).__name__}: {str(e)[:200]}"}
            return ""

    def generate(self, task):
        raw = self._call(self.primary, task)
        if not self.primary.last_call.get("error"):
            self.last_call = {**self.primary.last_call, "used": "primary", "model": self.primary.model,
                              "provenance": self._prov(self.primary, "primary")}
            return raw
        raw = self._call(self.fallback, task)
        self.last_call = {**self.fallback.last_call, "used": "fallback", "model": self.fallback.model,
                          "primary_error": self.primary.last_call["error"],
                          "provenance": self._prov(self.fallback, "fallback")}
        return raw
