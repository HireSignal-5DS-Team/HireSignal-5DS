"""Backends for candidates that are not decoder-only chat models. Same Task in, same raw-text contract out, so
the validator and metrics are unchanged.

- Seq2SeqBackend: encoder-decoder models (FLAN-T5 family). No chat template: the system and user messages of
  matcher.prompt are joined as plain text. Nothing about the architecture is changed.
- FermiBackend: Zerflyne/FERMI-0.8B, a classifier (Qwen3.5-0.8B + custom LoRA + decision head) that never
  generates text. It answers the requirement as a 3-way `choice` question. Its output is wrapped in the
  ModelAnswer JSON with evidence = [] and an explanation stating that it is a classifier, so a FERMI "MET" can
  never pass validation (MET needs a verified quote). The raw decision is kept for the raw-model metrics.
"""
import json
import time

from . import prompt
from .backends import MAX_PARAMS


class Seq2SeqBackend:
    def __init__(self, model_id, revision=None, max_new_tokens=192, device="cpu", dtype="float32"):
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        t0 = time.perf_counter()
        self.model_id, self.revision = model_id, revision
        self.tok = AutoTokenizer.from_pretrained(model_id, revision=revision)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_id, revision=revision, dtype=getattr(torch, dtype))
        self.n_params = sum(p.numel() for p in self.model.parameters())
        if self.n_params >= MAX_PARAMS:
            raise ValueError(f"{model_id} has {self.n_params:,} parameters; the Matcher requires < 1B")
        self.model.to(device).eval()
        self.device, self.max_new_tokens = device, max_new_tokens
        self.load_seconds = time.perf_counter() - t0

    def info(self):
        return {"backend": "seq2seq", "is_model": True, "model_id": self.model_id, "revision": self.revision,
                "adapter_id": None, "n_params": self.n_params, "device": self.device,
                "decoding": {"do_sample": False, "max_new_tokens": self.max_new_tokens},
                "load_seconds": round(self.load_seconds, 2), "prompt_version": prompt.PROMPT_VERSION,
                "prompt_format": "system + user joined as plain text (no chat template)"}

    def generate(self, task):
        import torch

        sys_msg, user = task.messages
        ids = self.tok(sys_msg["content"] + "\n\n" + user["content"], return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self.model.generate(**ids, max_new_tokens=self.max_new_tokens, do_sample=False)
        return self.tok.decode(out[0], skip_special_tokens=True)


OPTIONS = {"MET": "The CV clearly shows the requirement is satisfied.",
           "MISSING": "The CV shows the requirement is not met, or says nothing about it.",
           "UNCERTAIN": "The CV is unclear, partial or only implies it."}


class FermiBackend:
    """Decision-only arm. checkpoint = local folder of Zerflyne/FERMI-0.8B checkpoints/final; base = local Qwen3.5-0.8B."""

    def __init__(self, repo_dir, base_dir, checkpoint="checkpoints/final", device="cpu"):
        import sys

        t0 = time.perf_counter()
        sys.path.insert(0, str(repo_dir))
        from fermi import Fermi  # third-party package shipped in the model repo (read before use, see docs)

        self.m = Fermi.load(f"{repo_dir}/{checkpoint}", base=str(base_dir), device=device)
        self.repo_dir, self.checkpoint, self.device = str(repo_dir), checkpoint, device
        self.load_seconds = time.perf_counter() - t0

    def info(self):
        return {"backend": "fermi_classifier", "is_model": True, "model_id": "Zerflyne/FERMI-0.8B",
                "revision": "d21fa5400ff181083f5f8a07d82e6b8097f9cbc8", "adapter_id": f"FERMI {self.checkpoint} (custom LoRA + head)",
                "base_model": "Qwen/Qwen3.5-0.8B@2fc06364715b967f1860aea9cf38778875588b17", "device": self.device,
                "load_seconds": round(self.load_seconds, 2), "generates_text": False,
                "note": "decision-only classifier: no evidence, no explanation; MET cannot pass validation"}

    def generate(self, task):
        req = task.req
        years = f" (minimum {req.min_years:g} years)" if req.min_years else ""
        state = {"cv": task.cv.text,
                 "requirement": f"{req.text}{years}",
                 "knowledge (terminology only, not evidence)": [r.text[:300] for r in task.refs]}
        q = {"decision": {"type": "choice", "instructions": "Does the CV satisfy this job requirement?", "criteria": OPTIONS}}
        out = self.m.classify(state=state, questions=q)["decision"]
        d = out["answer"]
        basis = {"MET": "supported", "MISSING": "not_documented", "UNCERTAIN": "ambiguous"}[d]
        return json.dumps({"decision": d, "basis": basis, "evidence": [],
                           "explanation": f"FERMI classifier choice, p={out['probabilities']}"})
