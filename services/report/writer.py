"""Report Writer agent (station 7, T12): Qwen3-4B plain (the llama-server copy with LoRA scale 0: no extra GPU memory)
writes, the code fact checker reads (checker.py), one retry with the checker's error list, then the template.

Settings (env): REPORT_MODEL (default = LLM_MODEL, the plain Qwen3-4B), REPORT_BASE_URL (default = LLM_BASE_URL),
REPORT_LORA (1 = send LoRA scale 0, as for llama-server with the Matcher adapter loaded), REPORT_PROMPT
(prompts/report_writer/v3.md, chosen on dev in T13), REPORT_FALLBACK (template), REPORT_MAX_TOKENS (1400).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from services.config import env, llm_settings
from services.prompts import prompt_blocks

from .checker import check
from .record import llm_view
from .template import render

SCHEMA = json.loads((Path(__file__).with_name("schema.json")).read_text(encoding="utf-8"))
FALLBACK_FLAG = "report:template_fallback"


def _messages(blocks: dict, record: dict) -> list[dict]:
    msgs = [{"role": "system", "content": blocks["System"]}]
    if "Example user" in blocks:
        msgs += [{"role": "user", "content": blocks["Example user"]},
                 {"role": "assistant", "content": blocks["Example assistant"]}]
    view = json.dumps(llm_view(record), ensure_ascii=False)
    ids = ", ".join(r["req_id"] for r in record["requirements"])
    return msgs + [{"role": "user", "content": blocks["User template"].replace("{record}", view).replace("{req_ids}", ids)}]


def _call(messages: list[dict], client: httpx.Client, base_url: str, model: str, lora: bool, max_tokens: int) -> dict:
    body = {"model": model, "messages": messages, "temperature": 0, "top_p": 1, "seed": 0, "max_tokens": max_tokens,
            "response_format": {"type": "json_object", "schema": SCHEMA}}
    if lora:
        body["lora"] = [{"id": 0, "scale": 0}]  # the plain Qwen3-4B: the Matcher adapter is loaded but not applied
    t = time.perf_counter()
    r = client.post(base_url.rstrip("/") + "/chat/completions", json=body)
    r.raise_for_status()
    choice = r.json()["choices"][0]
    return {"raw": choice["message"]["content"], "finish": choice.get("finish_reason"),
            "latency_s": round(time.perf_counter() - t, 2)}


def _parse(raw: str) -> tuple[dict | None, list[str]]:
    try:
        rep = json.loads(raw)
    except ValueError:
        return None, ["the answer is not valid JSON"]
    if not isinstance(rep, dict) or set(SCHEMA["required"]) - set(rep):
        return None, ["the answer misses keys of the output schema"]
    return rep, []


def write_report(record: dict, prompt: str | None = None, client: httpx.Client | None = None,
                 base_url: str | None = None, model: str | None = None, lora: bool | None = None,
                 retry: bool = True) -> dict:
    """{report, source (llm | template), attempts, first_errors, retry_errors, latency_s, model, info_flags}."""
    cfg = llm_settings()
    prompt = prompt or env("REPORT_PROMPT", "prompts/report_writer/v3.md")
    base_url = base_url or env("REPORT_BASE_URL", cfg["base_url"])
    model = model or env("REPORT_MODEL", cfg["model"])
    lora = (env("REPORT_LORA", "1") == "1" and cfg["backend"] == "local") if lora is None else lora
    max_tokens = int(env("REPORT_MAX_TOKENS", "1400"))
    client = client or httpx.Client(timeout=cfg["timeout"])
    blocks = prompt_blocks(prompt)
    messages = _messages(blocks, record)
    t = time.perf_counter()
    out = {"model": model, "prompt": prompt, "attempts": 0, "first_errors": [], "retry_errors": [], "info_flags": []}
    errors = []
    for attempt in (1, 2):
        if attempt == 2 and (not retry or "Retry template" not in blocks):
            break
        try:
            call = _call(messages, client, base_url, model, lora, max_tokens)
        except httpx.HTTPError as exc:
            errors = [f"LLM call failed: {type(exc).__name__}"]
            out["first_errors" if attempt == 1 else "retry_errors"] = errors
            break
        out["attempts"] = attempt
        report, errors = _parse(call["raw"])
        if call["finish"] == "length":
            errors = errors + ["the answer was cut at the token limit"]
        if report is not None and not errors:
            errors = check(record, report)
        out["first_errors" if attempt == 1 else "retry_errors"] = errors
        out.setdefault("drafts", []).append(call["raw"])  # what the model wrote, for the evaluation
        if not errors:
            out |= {"report": report, "source": "llm", "latency_s": round(time.perf_counter() - t, 2)}
            return out
        messages = messages + [{"role": "assistant", "content": call["raw"]},
                               {"role": "user", "content": blocks.get("Retry template", "").replace(
                                   "{errors}", "\n".join(f"- {e}" for e in errors))}]
    if env("REPORT_FALLBACK", "template") != "template":
        raise RuntimeError(f"report failed the fact check: {errors}")
    out |= {"report": render(record), "source": "template", "latency_s": round(time.perf_counter() - t, 2),
            "info_flags": [FALLBACK_FLAG]}
    return out
