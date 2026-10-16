"""Frozen backbones and trainable soft prompts (PEFT prompt tuning: learned virtual-token embeddings).

Four arms, one loader, so every arm runs under the same backend, dtype and decoding:

  base              Qwen3-4B-Instruct-2507, frozen
  lora              base + Matcher LoRA, merged into the weights (merge_and_unload), frozen
  soft_prompt       base + soft prompt trained on the frozen base
  lora_soft_prompt  merged LoRA model + soft prompt trained on the frozen merged model

PEFT allows one adapter type per PeftModel, so the LoRA is merged first; the result is a plain Qwen3ForCausalLM and
prompt tuning wraps it like any base. A soft prompt records which backbone it was trained on (hs_soft_prompt.json)
and refuses to attach to another one: the virtual embeddings are tuned to that exact frozen network.
"""
import json
from pathlib import Path

from .common import config_hash

ARMS = ("base", "lora", "soft_prompt", "lora_soft_prompt")
SIDE_FILE = "hs_soft_prompt.json"


def backbone_id(base, revision, lora=None, lora_revision=None):
    """Identity of the frozen network a soft prompt is trained on / attached to."""
    return {"base": base, "base_revision": revision, "lora": lora, "lora_revision": lora_revision,
            "lora_merged": bool(lora)}


def load_backbone(base, revision=None, lora=None, lora_revision=None, dtype="float32", device="cpu",
                  check_lora_base=True):
    """Frozen (base [+ merged LoRA]) model, tokenizer and provenance. Every parameter has requires_grad=False."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(base, revision=revision)
    model = AutoModelForCausalLM.from_pretrained(base, revision=revision, dtype=getattr(torch, dtype))
    commit = getattr(model.config, "_commit_hash", None)
    lora_cfg = None
    if lora:
        from peft import PeftModel

        if check_lora_base:
            from matcher.backends import check_adapter_compat  # refuses a LoRA trained on another base

            lora_cfg = check_adapter_compat(lora, base, lora_revision)
        model = PeftModel.from_pretrained(model, lora, revision=lora_revision).merge_and_unload()
    model.to(device).eval()
    for p in model.parameters():
        p.requires_grad_(False)
    prov = {**backbone_id(base, revision, lora, lora_revision), "base_commit_hash": commit, "dtype": dtype,
            "n_params": sum(p.numel() for p in model.parameters()),
            "lora_r": getattr(lora_cfg, "r", None), "lora_alpha": getattr(lora_cfg, "lora_alpha", None)}
    return model, tok, prov


def new_soft_prompt(model, base, revision, num_virtual_tokens, init="text", init_text=None):
    """Wrap a frozen backbone with a fresh trainable soft prompt [num_virtual_tokens, hidden_size]."""
    from peft import PromptTuningConfig, PromptTuningInit, TaskType, get_peft_model

    kw = {}
    if init == "text":
        kw = {"prompt_tuning_init": PromptTuningInit.TEXT, "prompt_tuning_init_text": init_text,
              "tokenizer_name_or_path": base, "tokenizer_kwargs": {"revision": revision} if revision else None}
    elif init == "random":
        kw = {"prompt_tuning_init": PromptTuningInit.RANDOM}
    else:
        raise ValueError(f"init must be text|random, got {init!r}")
    cfg = PromptTuningConfig(task_type=TaskType.CAUSAL_LM, num_virtual_tokens=num_virtual_tokens, **kw)
    pm = get_peft_model(model, cfg)
    pm.prompt_encoder["default"].embedding.weight.data = pm.prompt_encoder["default"].embedding.weight.data.float()
    return pm


def trainable(pm):
    return [p for p in pm.parameters() if p.requires_grad]


def soft_prompt_tensor(pm):
    """The learned virtual-token embeddings, shape [num_virtual_tokens, hidden_size]."""
    return pm.get_prompt_embedding_to_save(adapter_name="default")


def save_soft_prompt(pm, out, backbone, extra=None):
    """PEFT adapter files + a plain safetensors export (no PEFT needed to read it) + the backbone it belongs to."""
    from safetensors.torch import save_file

    out = Path(out)
    pm.save_pretrained(out)
    t = soft_prompt_tensor(pm).detach().float().cpu().contiguous()
    save_file({"soft_prompt": t}, str(out / "soft_prompt.safetensors"))
    side = {"backbone": backbone, "shape": list(t.shape), **(extra or {})}
    side["backbone_hash"] = config_hash(backbone)
    (out / SIDE_FILE).write_text(json.dumps(side, indent=2) + "\n")
    return out


def check_soft_prompt_backbone(path, backbone):
    side = json.loads((Path(path) / SIDE_FILE).read_text())
    want = {k: side["backbone"].get(k) for k in ("base", "lora", "lora_merged")}
    have = {k: backbone.get(k) for k in ("base", "lora", "lora_merged")}
    norm = lambda d: {k: (str(v).replace("\\", "/").rstrip("/").split("/")[-2:] if isinstance(v, str) else v)  # noqa: E731
                      for k, v in d.items()}
    if norm(want) != norm(have):
        raise ValueError(f"soft prompt {path} was trained on {want}, refusing to attach to {have}")
    for k in ("base_revision", "lora_revision"):
        if side["backbone"].get(k) and backbone.get(k) and side["backbone"][k] != backbone[k]:
            raise ValueError(f"soft prompt {path} was trained on {k}={side['backbone'][k]}, got {backbone[k]}")
    return side


def load_soft_prompt(model, path, backbone, trainable_=False):
    from peft import PeftConfig, PeftModel

    cfg = PeftConfig.from_pretrained(path)
    if cfg.peft_type.value != "PROMPT_TUNING":
        raise ValueError(f"{path} is {cfg.peft_type}, not a prompt tuning adapter")
    check_soft_prompt_backbone(path, backbone)
    pm = PeftModel.from_pretrained(model, path, is_trainable=trainable_)
    return pm.eval() if not trainable_ else pm


def build_arm(arm, base, revision=None, lora=None, lora_revision=None, soft_prompt=None, dtype="float32",
              device="cpu", check_lora_base=True):
    """(model, tokenizer, provenance) for one arm; validates that the arm's ingredients are present and consistent."""
    if arm not in ARMS:
        raise ValueError(f"arm must be one of {ARMS}")
    uses_lora, uses_sp = arm in ("lora", "lora_soft_prompt"), arm in ("soft_prompt", "lora_soft_prompt")
    if uses_lora != bool(lora):
        raise ValueError(f"arm {arm} {'needs' if uses_lora else 'must not get'} --lora")
    if uses_sp != bool(soft_prompt):
        raise ValueError(f"arm {arm} {'needs' if uses_sp else 'must not get'} --soft-prompt")
    model, tok, prov = load_backbone(base, revision, lora, lora_revision, dtype, device, check_lora_base)
    prov["arm"], prov["soft_prompt"] = arm, None
    if uses_sp:
        side = check_soft_prompt_backbone(soft_prompt, prov)
        model = load_soft_prompt(model, soft_prompt, prov).to(device)
        from .common import sha256

        prov["soft_prompt"] = {"path": str(soft_prompt), "shape": side["shape"],
                               "sha256": sha256(Path(soft_prompt) / "soft_prompt.safetensors"),
                               "train_config_hash": side.get("train_config_hash")}
    return model, tok, prov
