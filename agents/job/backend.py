"""How the Job Agent talks to NuExtract.

One OpenAI-compatible client covers every way of running the model:
  - llama.cpp server on your laptop   (llama-server -m NuExtract-2.0-2B-Q4_K_M.gguf --jinja)
  - vLLM, or a hosted API

Two modes for sending the template:
  "kwargs"  the official way (model card): template and examples go in
            chat_template_kwargs, and the model's own chat template builds the prompt.
            Needs a server that supports it (vLLM; llama.cpp with --jinja).
  "inline"  fallback: we write the "# Template / # Examples / # Context" layout
            ourselves in the user message, for servers that ignore chat_template_kwargs.

Settings come from arguments or environment variables:
  HS_NUEXTRACT_BASE_URL   default http://127.0.0.1:8080/v1
  HS_NUEXTRACT_MODEL      default NuExtract-2.0-2B
  HS_NUEXTRACT_MODE       kwargs | inline   (default kwargs)
  HS_NUEXTRACT_API_KEY    only for hosted APIs (never logged)
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Protocol

SYSTEM_PROMPT = "You are NuExtract, an information extraction tool created by NuMind."


class ExtractionBackend(Protocol):
    def extract(self, text: str, template: str, examples: list[dict]) -> str:
        """Return the model's raw answer (expected: a JSON string)."""


class BackendError(Exception):
    """The model server could not be reached or answered with an error."""


def build_inline_prompt(text: str, template: str, examples: list[dict]) -> str:
    """The NuExtract layout written by hand (used by the 'inline' mode)."""
    parts = ["# Template:", template]
    if examples:
        parts.append("# Examples:")
        for ex in examples:
            parts += ["## Input:", ex["input"], "## Output:", ex["output"]]
    parts += ["# Context:", text]
    return "\n".join(parts)


class NuExtractClient:
    """Calls NuExtract through an OpenAI-compatible /chat/completions endpoint."""

    def __init__(self, base_url: str | None = None, model: str | None = None,
                 mode: str | None = None, timeout: float = 180.0, max_tokens: int = 2048,
                 seed: int = 0):
        self.base_url = (base_url or os.environ.get("HS_NUEXTRACT_BASE_URL",
                                                    "http://127.0.0.1:8080/v1")).rstrip("/")
        self.model = model or os.environ.get("HS_NUEXTRACT_MODEL", "NuExtract-2.0-2B")
        self.mode = mode or os.environ.get("HS_NUEXTRACT_MODE", "kwargs")
        if self.mode not in ("kwargs", "inline"):
            raise ValueError("mode must be 'kwargs' or 'inline'")
        self.timeout, self.max_tokens, self.seed = timeout, max_tokens, seed
        self.last_call: dict = {}
        self.last_raw: str = ""   # the model's raw answer, saved for debugging and the prompt library

    def _payload(self, text: str, template: str, examples: list[dict]) -> dict:
        payload = {
            "model": self.model,
            "temperature": 0,          # the model card asks for temperature 0
            "top_p": 1,
            "seed": self.seed,         # fixed seed: same input -> same output (measured: temperature 0
                                       # alone was not enough with Ollama's CPU/GPU split)
            "max_tokens": self.max_tokens,
        }
        if self.mode == "kwargs":
            payload["messages"] = [{"role": "user", "content": text}]
            payload["chat_template_kwargs"] = {"template": template, "examples": examples}
        else:
            payload["messages"] = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_inline_prompt(text, template, examples)},
            ]
        return payload

    def extract(self, text: str, template: str, examples: list[dict]) -> str:
        headers = {"Content-Type": "application/json"}
        key = os.environ.get("HS_NUEXTRACT_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(self._payload(text, template, examples)).encode("utf-8"),
            headers=headers,
        )
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise BackendError(f"NuExtract server error {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BackendError(
                f"Cannot reach NuExtract at {self.base_url} ({exc}). Is llama-server running?"
            ) from exc

        usage = body.get("usage") or {}
        self.last_call = {
            "latency_s": round(time.perf_counter() - start, 2),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "mode": self.mode,
        }
        try:
            self.last_raw = body["choices"][0]["message"]["content"] or ""
            # "length" = the answer hit max_tokens and was cut off
            self.last_call["finish_reason"] = body["choices"][0].get("finish_reason")
            return self.last_raw
        except (KeyError, IndexError, TypeError) as exc:
            raise BackendError(f"Unexpected answer from the server: {str(body)[:300]}") from exc

    def info(self) -> dict:
        return {"model": self.model, "mode": self.mode,
                "base_url": self.base_url if "127.0.0.1" in self.base_url or "localhost" in self.base_url
                else "<hosted>"}


class FakeBackend:
    """Prepared answers for the tests (no GPU needed).

    answers: a list returned in order, or a function (text, template) -> answer,
    for the chunked strategy where the answer depends on the chunk.
    """

    def __init__(self, answers):
        self.answers = answers if callable(answers) else list(answers)
        self.calls: list[dict] = []
        self.last_call: dict = {}
        self.last_raw = ""

    def extract(self, text: str, template: str, examples: list[dict]) -> str:
        self.calls.append({"text": text, "template": template, "examples": examples})
        if callable(self.answers):
            self.last_raw = self.answers(text, template)
            return self.last_raw
        if not self.answers:
            raise BackendError("FakeBackend has no more answers")
        self.last_raw = self.answers.pop(0)
        return self.last_raw

    def info(self) -> dict:
        return {"model": "fake", "mode": "fake"}
