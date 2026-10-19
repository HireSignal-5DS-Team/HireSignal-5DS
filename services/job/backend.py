# Adapted from team V2: agents/job/backend.py (feature/agent-integration @ a5a03ff)
"""How the Profile and Job agents talk to their model: the plain Qwen3-4B on our llama-server.

Changes vs V2: NuExtract client and make_backend removed (only V2's job-q1 path is used); settings come from our
.env (services/config.py); every request carries the llama-server LoRA scale explicitly (0 = plain model), because a
request without a "lora" field uses the server's global scale (measured in T02b).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Protocol

from services.config import llm_settings


class ExtractionBackend(Protocol):
    def extract(self, text: str, template: str, examples: list[dict]) -> str:
        """Return the model's raw answer (expected: a JSON string)."""


class BackendError(Exception):
    """The model server could not be reached or answered with an error."""


_TYPE_HELP = (
    "Field types in the template: \"verbatim-string\" = copy the text EXACTLY as it appears in the input, "
    "character for character; \"string\" = short free text; \"number\" = a number or null; "
    "a list of options = choose exactly one of them; a list containing a type = a list of values of that type "
    "(empty list if none). If a value is not in the input, use null (or an empty list)."
)


def template_to_instructions(template: str) -> str:
    """A NuExtract-style typed template (the job-title call) as instructions for a chat model."""
    return ("Extract information from the input into JSON that follows this template exactly "
            "(same keys, no extra keys):\n" + template + "\n" + _TYPE_HELP +
            "\nAnswer with the JSON object only.")


class QwenChatClient:
    """The plain Qwen3-4B-Instruct (LoRA scale 0) on llama-server, OpenAI-compatible /chat/completions.

    `template` is either plain instructions (job-v1, profile-v1) or a NuExtract-style JSON template
    (the title call), which is turned into instructions. Examples become user/assistant turns (few-shot).

    The Matcher's LoRA is trained to answer matching questions, not to read CVs or job offers:
    a non-zero LoRA scale is refused.
    """

    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: float | None = None,
                 max_tokens: int = 2048, seed: int = 0, json_mode: bool | None = None,
                 lora_scale: float | None = 0.0):
        cfg = llm_settings()
        self.base_url = (base_url or cfg["base_url"]).rstrip("/")
        self.model = model or cfg["model"]
        self.api_key = cfg["api_key"]
        if lora_scale not in (0, 0.0, None):
            raise ValueError(f"LoRA scale {lora_scale} is the Matcher. The Profile and Job agents must use the "
                             f"plain Qwen (scale 0).")
        # cloud backup has no adapters: no "lora" field at all
        self.lora_scale = None if cfg["backend"] == "cloud" else lora_scale
        if json_mode is None:
            json_mode = os.environ.get("LLM_JSON_MODE", "1") != "0"
        self.timeout = timeout if timeout is not None else cfg["timeout"]
        self.max_tokens, self.seed, self.json_mode = max_tokens, seed, json_mode
        self.mode = "chat"
        self.last_call: dict = {}
        self.last_raw: str = ""

    def _messages(self, text: str, template: str, examples: list[dict]) -> list[dict]:
        system = template if not template.lstrip().startswith("{") else template_to_instructions(template)
        messages = [{"role": "system", "content": system}]
        for ex in examples:
            messages += [{"role": "user", "content": ex["input"]},
                         {"role": "assistant", "content": ex["output"]}]
        messages.append({"role": "user", "content": text})
        return messages

    def _payload(self, text: str, template: str, examples: list[dict]) -> dict:
        payload = {"model": self.model, "messages": self._messages(text, template, examples),
                   "temperature": 0, "top_p": 1, "seed": self.seed, "max_tokens": self.max_tokens}
        if self.lora_scale is not None:
            payload["lora"] = [{"id": 0, "scale": self.lora_scale}]
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def extract(self, text: str, template: str, examples: list[dict]) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(f"{self.base_url}/chat/completions",
                                         data=json.dumps(self._payload(text, template, examples)).encode("utf-8"),
                                         headers=headers)
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            hint = " (try LLM_JSON_MODE=0)" if "response_format" in detail else ""
            raise BackendError(f"Qwen server error {exc.code}: {detail}{hint}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BackendError(f"Cannot reach Qwen at {self.base_url} ({exc}). Is the server running?") from exc

        usage = body.get("usage") or {}
        self.last_call = {"latency_s": round(time.perf_counter() - start, 2),
                          "prompt_tokens": usage.get("prompt_tokens"),
                          "completion_tokens": usage.get("completion_tokens"), "mode": "chat"}
        try:
            self.last_raw = body["choices"][0]["message"]["content"] or ""
            self.last_call["finish_reason"] = body["choices"][0].get("finish_reason")
            return self.last_raw
        except (KeyError, IndexError, TypeError) as exc:
            raise BackendError(f"Unexpected answer from the server: {str(body)[:300]}") from exc

    def info(self) -> dict:
        local = "127.0.0.1" in self.base_url or "localhost" in self.base_url
        return {"model": self.model, "mode": "chat", "lora_scale": self.lora_scale,
                "base_url": self.base_url if local else "<hosted>"}


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
