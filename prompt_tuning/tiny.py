"""A RANDOMLY INITIALISED TINY Qwen3 model (hidden 64, 2 layers, tied embeddings like Qwen3-4B) with a locally trained
byte-level BPE tokenizer and a ChatML template. For plumbing tests and the CPU smoke run ONLY: its outputs are noise.
"""
from pathlib import Path

TEMPLATE = ("{% for m in messages %}<|im_start|>{{ m['role'] }}\n{{ m['content'] }}<|im_end|>\n{% endfor %}"
            "{% if add_generation_prompt %}<|im_start|>assistant\n{% endif %}")


def tiny_qwen3(path, texts, seed=0, vocab_size=400):
    import torch
    from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers
    from transformers import PreTrainedTokenizerFast, Qwen3Config, Qwen3ForCausalLM

    path = Path(path)
    if (path / "config.json").exists():
        return str(path)
    specials = ["<|endoftext|>", "<|im_start|>", "<|im_end|>"]
    t = Tokenizer(models.BPE())
    t.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    t.decoder = decoders.ByteLevel()
    t.train_from_iterator(texts, trainers.BpeTrainer(vocab_size=vocab_size, special_tokens=specials,
                                                     initial_alphabet=pre_tokenizers.ByteLevel.alphabet()))
    tok = PreTrainedTokenizerFast(tokenizer_object=t, eos_token="<|im_end|>", pad_token="<|endoftext|>")
    tok.chat_template = TEMPLATE
    torch.manual_seed(seed)
    cfg = Qwen3Config(vocab_size=len(tok), hidden_size=64, intermediate_size=128, num_hidden_layers=2,
                      num_attention_heads=4, num_key_value_heads=2, head_dim=16, max_position_embeddings=4096,
                      eos_token_id=tok.eos_token_id, pad_token_id=tok.pad_token_id, tie_word_embeddings=True)
    Qwen3ForCausalLM(cfg).save_pretrained(path)
    tok.save_pretrained(path)
    return str(path)


def tiny_lora(base, path, seed=1):
    """A random (non-zero) PEFT LoRA adapter for the tiny base, standing in for the Matcher LoRA in tests."""
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM

    path = Path(path)
    if (path / "adapter_config.json").exists():
        return str(path)
    torch.manual_seed(seed)
    m = get_peft_model(AutoModelForCausalLM.from_pretrained(base), LoraConfig(
        r=4, lora_alpha=8, task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]))
    with torch.no_grad():
        for n, p in m.named_parameters():
            if "lora_B" in n:
                p.normal_(0, 0.05)  # default init is B = 0 (a no-op adapter); make the merge change the weights
    m.save_pretrained(path)
    return str(path)
