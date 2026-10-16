"""Compatibility check (no model weights downloaded): tokenizer + chat template, PEFT version, the Matcher LoRA's
adapter config, the soft prompt shape. Writes benchmark/results/experimental/soft_prompt/compat_check.json.

  python -m prompt_tuning.compat_check
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from .common import BASE, BASE_REVISION, LORA, LORA_REVISION, RESULTS, ROOT, SFT_TRAIN, SFT_VAL, read_jsonl

QWEN3_LINEAR = {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"}


def pinned(name):
    m = re.search(rf"^{re.escape(name)}==([^\s#]+)", (ROOT / "requirements-matcher.txt").read_text(), re.M)
    return m.group(1) if m else None


def fhash(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(RESULTS / "compat_check.json"))
    a = ap.parse_args(argv)
    import peft
    import transformers
    from huggingface_hub import hf_hub_download
    from peft import PromptTuningConfig  # noqa: F401  (import check)
    from transformers import AutoTokenizer

    get = lambda repo, rev, f: hf_hub_download(repo, f, revision=rev)  # noqa: E731
    base_cfg = json.loads(Path(get(BASE, BASE_REVISION, "config.json")).read_text())
    for f in ("tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt"):
        get(BASE, BASE_REVISION, f)
    lcfg = json.loads(Path(get(LORA, LORA_REVISION, "adapter_config.json")).read_text())
    ltok_json = get(LORA, LORA_REVISION, "tokenizer.json")
    lmeta = json.loads(Path(get(LORA, LORA_REVISION, "train_meta.json")).read_text())
    ltemplate = Path(get(LORA, LORA_REVISION, "chat_template.jinja")).read_text()

    tok = AutoTokenizer.from_pretrained(BASE, revision=BASE_REVISION)
    ex = read_jsonl(SFT_TRAIN)[0]
    with_flag = tok.apply_chat_template(ex["messages"][:2], tokenize=False, add_generation_prompt=True, enable_thinking=False)
    without = tok.apply_chat_template(ex["messages"][:2], tokenize=False, add_generation_prompt=True)
    base_tok_json = get(BASE, BASE_REVISION, "tokenizer.json")
    ltok = AutoTokenizer.from_pretrained(LORA, revision=LORA_REVISION)
    texts = [tok.apply_chat_template(e["messages"], tokenize=False) for e in read_jsonl(SFT_TRAIN) + read_jsonl(SFT_VAL)]
    same_ids = sum(tok(t, add_special_tokens=False)["input_ids"] == ltok(t, add_special_tokens=False)["input_ids"]
                   for t in texts)
    checks = {
        "base_architecture": base_cfg["architectures"],
        "hidden_size": base_cfg["hidden_size"], "tie_word_embeddings": base_cfg["tie_word_embeddings"],
        "soft_prompt_shape_for_32_tokens": [32, base_cfg["hidden_size"]],
        "chat_template_enable_thinking_flag_is_noop": with_flag == without,
        "rendered_prompt_has_think_block": "<think>" in with_flag,
        "generation_prompt_suffix": with_flag[-len("<|im_start|>assistant\n"):] == "<|im_start|>assistant\n",
        "eos_token": tok.eos_token, "pad_token": tok.pad_token,
        "lora_tokenizer_json_byte_identical_to_base": fhash(ltok_json) == fhash(base_tok_json),
        "lora_tokenizer_same_vocab": ltok.get_vocab() == tok.get_vocab(),
        "lora_tokenizer_same_special_tokens": [ltok.eos_token, ltok.pad_token] == [tok.eos_token, tok.pad_token],
        "lora_tokenizer_identical_ids_on_sft_train_and_val": f"{same_ids}/{len(texts)}",
        "_identical_ids_all": same_ids == len(texts),
        "lora_chat_template_identical_to_base": ltemplate.strip() == (tok.chat_template or "").strip(),
        "lora_peft_type": lcfg["peft_type"], "lora_base": lcfg["base_model_name_or_path"],
        "lora_base_matches": lcfg["base_model_name_or_path"] == BASE,
        "lora_trained_on_revision": lmeta.get("revision"),
        "lora_revision_matches_pinned_base": lmeta.get("revision") == BASE_REVISION,
        "lora_targets_are_qwen3_linears": set(lcfg["target_modules"]) <= QWEN3_LINEAR,
        "lora_r_alpha": [lcfg["r"], lcfg["lora_alpha"]], "lora_peft_version": lcfg.get("peft_version"),
        "lora_training_quantisation": "4-bit NF4 + fp16 compute (QLoRA, Kaggle), per the adapter README",
        "lora_training_data": lmeta["data_manifest"]["files"]["sft_train.jsonl"],
        "peft_pinned": pinned("peft"), "peft_installed": peft.__version__,
        "transformers_pinned": pinned("transformers"), "transformers_installed": transformers.__version__,
        "peft_pin_matches_lora": pinned("peft") == lcfg.get("peft_version"),
    }
    ok = all(checks[k] for k in ("chat_template_enable_thinking_flag_is_noop", "generation_prompt_suffix",
                                 "lora_tokenizer_same_vocab", "lora_tokenizer_same_special_tokens",
                                 "_identical_ids_all", "lora_base_matches",
                                 "lora_revision_matches_pinned_base", "lora_targets_are_qwen3_linears",
                                 "peft_pin_matches_lora")) and not checks["rendered_prompt_has_think_block"]
    res = {"base": BASE, "base_revision": BASE_REVISION, "lora": LORA, "lora_revision": LORA_REVISION,
           "all_ok": ok, "checks": checks, "label": "MEASURED (metadata + tokenizer only; no weights loaded)"}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2) + "\n")
    print(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    main()
