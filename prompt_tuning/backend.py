"""Generation backend for the four experimental arms (transformers, greedy). Same interface as matcher/backends.py
(generate(task) -> raw text, info()), so it can be plugged into matcher.agent.Matcher for an opt-in experiment.

Why not matcher.backends.TransformersBackend: it refuses models >= 1B parameters (MAX_PARAMS, the < 1B Matcher rule
of the original design) and knows only LoRA adapters. The production Qwen3-4B Matcher is served by llama.cpp (GGUF),
which cannot load PEFT prompt embeddings, so the soft prompt arms need this transformers path; for a fair comparison
the base and LoRA arms are re-run through this same backend, same dtype, same device.
"""
import time

from .model import build_arm


class SoftPromptBackend:
    def __init__(self, arm, base, revision=None, lora=None, lora_revision=None, soft_prompt=None, dtype="float32",
                 device="cpu", max_new_tokens=192, check_lora_base=True):
        t0 = time.perf_counter()
        self.model, self.tok, self.prov = build_arm(arm, base, revision, lora, lora_revision, soft_prompt, dtype,
                                                    device, check_lora_base)
        self.arm, self.device, self.dtype, self.max_new_tokens = arm, device, dtype, max_new_tokens
        self.chat_kwargs = {"enable_thinking": False}  # ignored by templates without the flag (Instruct-2507)
        self.load_seconds = time.perf_counter() - t0
        self.last_call = None

    def info(self):
        from matcher import prompt

        sp = self.prov.get("soft_prompt") or {}
        return {"backend": "transformers_softprompt", "experimental": True, "is_model": True, "arm": self.arm,
                "model_id": self.prov["base"], "revision": self.prov["base_revision"],
                "adapter_id": self.prov["lora"], "adapter_revision": self.prov["lora_revision"],
                "lora_merged": self.prov["lora_merged"], "soft_prompt": sp or None, "dtype": self.dtype,
                "device": self.device, "n_params": self.prov["n_params"],
                "decoding": {"do_sample": False, "max_new_tokens": self.max_new_tokens},
                "load_seconds": round(self.load_seconds, 2), "prompt_version": prompt.PROMPT_VERSION}

    def render(self, messages):
        return self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, **self.chat_kwargs)

    def generate_messages(self, messages):
        import torch

        ids = self.tok(self.render(messages), return_tensors="pt", add_special_tokens=False).to(self.device)
        with torch.no_grad():
            out = self.model.generate(input_ids=ids["input_ids"], attention_mask=ids["attention_mask"],
                                      max_new_tokens=self.max_new_tokens, do_sample=False,
                                      pad_token_id=self.tok.pad_token_id or self.tok.eos_token_id)
        n_in = ids["input_ids"].shape[1]
        new = out[0, n_in:] if out.shape[1] > n_in else out[0]  # PEFT returns input ids + new ids (no virtual ids)
        self.last_call = {"prompt_tokens": n_in, "completion_tokens": int(new.shape[0])}
        return self.tok.decode(new, skip_special_tokens=True)

    def generate(self, task):
        return self.generate_messages(task.messages)
