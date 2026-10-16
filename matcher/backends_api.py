"""OpenAI-compatible chat backend for the Matcher (Qwen3-4B-Instruct-2507).

One code path serves:
- local inference: llama.cpp server (`python -m llama_cpp.server --model <gguf>`), vLLM, Ollama (`/v1`), or
- a hosted API (any OpenAI-compatible /v1/chat/completions endpoint).

Configuration (constructor args or environment): base_url (HS_LLM_BASE_URL), model (HS_LLM_MODEL),
api key read from the env var named by api_key_env (default HS_LLM_API_KEY; never stored or logged).
Greedy decoding (temperature 0), bounded retries with exponential backoff, per-call timeout.
After each call `last_call` holds {latency_s, prompt_tokens, completion_tokens, error, attempts}.
On final failure generate() returns "" so the validator records `model_output_invalid` (no fabricated decision).
"""
import json
import os
import time
import urllib.error
import urllib.request

from . import prompt


class OpenAICompatBackend:
    def __init__(self, base_url=None, model=None, api_key_env="HS_LLM_API_KEY", timeout=120.0, max_retries=2,
                 max_tokens=192, label=None, price_per_mtok=None, provider="local"):
        self.base_url = (base_url or os.environ.get("HS_LLM_BASE_URL", "http://127.0.0.1:8080/v1")).rstrip("/")
        self.model = model or os.environ.get("HS_LLM_MODEL", "Qwen/Qwen3-4B-Instruct-2507")
        self.api_key_env, self.timeout, self.max_retries, self.max_tokens = api_key_env, timeout, max_retries, max_tokens
        self.label, self.provider = label or self.model, provider
        self.price_per_mtok = price_per_mtok  # (input, output) USD per 1M tokens, only for cost estimates
        self.last_call, self.totals = {}, {"calls": 0, "errors": 0, "prompt_tokens": 0, "completion_tokens": 0}

    def info(self):
        return {"backend": "openai_compat", "is_model": True, "model_id": self.model, "label": self.label,
                "provider": self.provider, "base_url": self.base_url if self.provider == "local" else "<hosted>",
                "decoding": {"temperature": 0, "max_tokens": self.max_tokens}, "timeout_s": self.timeout,
                "max_retries": self.max_retries, "prompt_version": prompt.PROMPT_VERSION, "adapter_id": None,
                "revision": os.environ.get("HS_LLM_REVISION")}

    def _post(self, payload):
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(self.api_key_env)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        req = urllib.request.Request(f"{self.base_url}/chat/completions", data=json.dumps(payload).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())

    def chat(self, messages, max_tokens=None):
        payload = {"model": self.model, "messages": messages, "temperature": 0, "top_p": 1,
                   "max_tokens": max_tokens or self.max_tokens, "seed": 0}
        t0, err = time.perf_counter(), None
        for attempt in range(1, self.max_retries + 2):
            try:
                out = self._post(payload)
                usage = out.get("usage") or {}
                self._record(t0, attempt, None, usage)
                return out["choices"][0]["message"]["content"] or ""
            except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, json.JSONDecodeError) as e:
                err = f"{type(e).__name__}: {str(e)[:200]}"
                if isinstance(e, urllib.error.HTTPError) and e.code in (400, 401, 403, 404):
                    break  # not retryable
                if attempt <= self.max_retries:
                    time.sleep(min(2 ** attempt, 20))
        self._record(t0, attempt, err, {})
        return ""

    def _record(self, t0, attempt, err, usage):
        self.last_call = {"latency_s": round(time.perf_counter() - t0, 3), "attempts": attempt, "error": err,
                          "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens")}
        t = self.totals
        t["calls"] += 1
        t["errors"] += err is not None
        t["prompt_tokens"] += usage.get("prompt_tokens") or 0
        t["completion_tokens"] += usage.get("completion_tokens") or 0

    def generate(self, task):
        return self.chat(task.messages)


class FallbackBackend:
    """Primary Matcher model with a fallback (e.g. fine-tuned LoRA endpoint -> original Qwen3-4B endpoint).
    Falls back ONLY on a transport failure of the primary (error after its retries), never on a model answer the
    validator dislikes. `last_call["used"]` records which model produced each answer, so reports cite it."""

    def __init__(self, primary, fallback):
        self.primary, self.fallback = primary, fallback
        self.last_call = {}

    def info(self):
        return {"backend": "fallback", "is_model": True, "primary": self.primary.info(), "fallback": self.fallback.info(),
                "model_id": self.primary.info().get("model_id"), "prompt_version": prompt.PROMPT_VERSION}

    def generate(self, task):
        raw = self.primary.generate(task)
        if not self.primary.last_call.get("error"):
            self.last_call = {**self.primary.last_call, "used": "primary", "model": self.primary.model}
            return raw
        raw = self.fallback.generate(task)
        self.last_call = {**self.fallback.last_call, "used": "fallback", "model": self.fallback.model,
                          "primary_error": self.primary.last_call["error"]}
        return raw
