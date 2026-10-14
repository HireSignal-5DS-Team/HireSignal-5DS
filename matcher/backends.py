"""Decision backends. Each returns the raw text the validator parses, so every backend goes through the same rules.

- TransformersBackend: the ONE generative SLM (< 1B params) + optional PEFT LoRA adapter of the same base.
- LexicalBaseline: deterministic keyword matcher (no neural model), a reference baseline for the benchmark.
- MockBackend: scripted outputs for orchestration tests ONLY. Never report its numbers as model results.
"""
import json
import re
import time
from dataclasses import dataclass

from . import prompt

MAX_PARAMS = 1_000_000_000


@dataclass
class Task:
    cv: object
    req: object
    refs: list

    @property
    def messages(self):
        return prompt.messages(self.cv, self.req, self.refs)


class MockBackend:
    def __init__(self, fn, label="mock"):
        self.fn, self.label = fn, label

    def info(self):
        return {"backend": "mock", "label": self.label, "is_model": False}

    def generate(self, task):
        return self.fn(task)


def _lines(text):
    """(line, start) pairs; a line is the unit quoted by the lexical baseline."""
    pos = 0
    for line in text.splitlines(keepends=True):
        if line.strip():
            yield line.strip(), pos + line.index(line.strip())
        pos += len(line)


class LexicalBaseline:
    """MET if a requirement term or ESCO alias occurs (word-bounded) in a CV line; MISSING/not_documented otherwise.
    With min_years, years parsed from that line decide MET vs MISSING/contradicted."""

    def info(self):
        return {"backend": "lexical_baseline", "is_model": False}

    def generate(self, task):
        from .validate import evidence_years

        terms = [t for t in [*task.req.skill_terms, *(a for r in task.refs for a in [r.title, *r.aliases])] if len(t) >= 2]
        for line, _ in _lines(task.cv.text):
            if any(re.search(rf"(?<!\w){re.escape(t)}(?!\w)", line, re.I) for t in terms):
                yrs = evidence_years([line]) if task.req.min_years else None
                if yrs is not None and yrs < task.req.min_years:
                    return json.dumps({"decision": "MISSING", "basis": "contradicted", "evidence": [line],
                                       "explanation": f"CV line shows {yrs:g} years, below {task.req.min_years:g}."})
                return json.dumps({"decision": "MET", "basis": "supported", "evidence": [line],
                                   "explanation": "Requirement term found in the CV."})
        return json.dumps({"decision": "MISSING", "basis": "not_documented", "evidence": [],
                           "explanation": "No requirement term found in the CV."})


def check_adapter_compat(adapter_id, base_id, revision=None):
    """Refuse an adapter whose adapter_config.json names another base model (or is not a LoRA adapter)."""
    from peft import PeftConfig

    cfg = PeftConfig.from_pretrained(adapter_id, revision=revision)
    if cfg.peft_type.value != "LORA":
        raise ValueError(f"{adapter_id} is {cfg.peft_type}, not a LoRA adapter")
    declared = (cfg.base_model_name_or_path or "").rstrip("/")
    if declared.split("/")[-2:] != base_id.rstrip("/").split("/")[-2:]:
        raise ValueError(f"{adapter_id} was trained on {declared!r}, refusing to attach to {base_id!r}")
    return cfg


class TransformersBackend:
    def __init__(self, model_id, adapter_id=None, revision=None, adapter_revision=None, max_new_tokens=192,
                 device="cpu", dtype="float32", chat_kwargs=None, allow_local_adapter_base_mismatch=False):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        t0 = time.perf_counter()
        self.model_id, self.adapter_id, self.revision, self.adapter_revision = model_id, adapter_id, revision, adapter_revision
        self.tok = AutoTokenizer.from_pretrained(model_id, revision=revision)
        self.model = AutoModelForCausalLM.from_pretrained(model_id, revision=revision, dtype=getattr(torch, dtype))
        self.n_params = sum(p.numel() for p in self.model.parameters())
        if self.n_params >= MAX_PARAMS:
            raise ValueError(f"{model_id} has {self.n_params:,} parameters; the Matcher requires < 1B")
        if adapter_id:
            from peft import PeftModel

            if not allow_local_adapter_base_mismatch:
                check_adapter_compat(adapter_id, model_id, adapter_revision)
            self.model = PeftModel.from_pretrained(self.model, adapter_id, revision=adapter_revision)
        self.model.to(device).eval()
        self.device, self.max_new_tokens = device, max_new_tokens
        # Qwen3: disable thinking so the reply is the JSON object; ignored by templates without the flag
        self.chat_kwargs = {"enable_thinking": False, **(chat_kwargs or {})}
        self.load_seconds = time.perf_counter() - t0

    def info(self):
        return {"backend": "transformers", "is_model": True, "model_id": self.model_id, "revision": self.revision,
                "adapter_id": self.adapter_id, "adapter_revision": self.adapter_revision, "n_params": self.n_params,
                "decoding": {"do_sample": False, "max_new_tokens": self.max_new_tokens}, "device": self.device,
                "load_seconds": round(self.load_seconds, 2), "prompt_version": prompt.PROMPT_VERSION}

    def generate(self, task):
        import torch

        text = self.tok.apply_chat_template(task.messages, tokenize=False, add_generation_prompt=True, **self.chat_kwargs)
        ids = self.tok(text, return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self.model.generate(**ids, max_new_tokens=self.max_new_tokens, do_sample=False,
                                      pad_token_id=self.tok.pad_token_id or self.tok.eos_token_id)
        return self.tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)
