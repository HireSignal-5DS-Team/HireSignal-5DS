"""QLoRA SFT of Qwen/Qwen3-4B-Instruct-2507 for the HireSignal Matcher (Kaggle GPU: T4 x2 / P100, 16 GB).

- Trains ONLY on finetuning/data/sft_train.jsonl; sft_dev.jsonl gives eval loss. Any other file is refused.
- Loss on the assistant JSON only (prompt tokens masked with -100). The prompt is rendered with the model's chat
  template exactly as at inference (add_generation_prompt=True).
- 4-bit NF4 base (bitsandbytes), LoRA r=16 / alpha=32 / dropout 0.05 on all linear projections, fp16 compute
  (T4/P100 have no bf16), gradient checkpointing, paged AdamW 8-bit. Checkpoints every --save-steps; re-running
  the same command resumes from the last checkpoint.

  python -m finetuning.train_qlora --out /kaggle/working/qwen3-4b-hs-lora
"""
import argparse
import json
import math
from pathlib import Path

DATA = Path(__file__).parent / "data"
BASE = "Qwen/Qwen3-4B-Instruct-2507"
TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def read(name):
    assert name in ("sft_train.jsonl", "sft_dev.jsonl"), f"refusing to train/evaluate on {name}"
    return [json.loads(x) for x in (DATA / name).read_text(encoding="utf-8").splitlines() if x.strip()]


def encode(tok, ex, max_len):
    *msgs, ans = ex["messages"]
    p = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    p_ids = tok(p, add_special_tokens=False)["input_ids"]
    t_ids = tok(ans["content"] + "<|im_end|>\n", add_special_tokens=False)["input_ids"]
    if len(p_ids) + len(t_ids) > max_len:
        return None  # never truncate a CV or a target
    return {"input_ids": p_ids + t_ids, "labels": [-100] * len(p_ids) + t_ids}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--revision", default=None, help="pin the base commit (record it in your report)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=float, default=2)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--grad-accum", type=int, default=16)
    ap.add_argument("--max-len", type=int, default=1024)
    ap.add_argument("--r", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=32)
    ap.add_argument("--save-steps", type=int, default=20)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--no-4bit", action="store_true", help="smoke tests on CPU with a tiny model only")
    a = ap.parse_args(argv)

    import torch
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (AutoModelForCausalLM, AutoTokenizer, DataCollatorForSeq2Seq, Trainer,
                              TrainingArguments, set_seed)

    set_seed(a.seed)
    tok = AutoTokenizer.from_pretrained(a.base, revision=a.revision)
    tok.pad_token = tok.pad_token or tok.eos_token
    kw = {}
    if not a.no_4bit:
        from transformers import BitsAndBytesConfig

        kw["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                                       bnb_4bit_compute_dtype=torch.float16, bnb_4bit_use_double_quant=True)
        kw["device_map"] = "auto"
    model = AutoModelForCausalLM.from_pretrained(a.base, revision=a.revision, dtype=torch.float16 if not a.no_4bit else torch.float32, **kw)
    if not a.no_4bit:
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    targets = [t for t in TARGETS if any(n.endswith(t) for n, _ in model.named_modules())]
    model = get_peft_model(model, LoraConfig(r=a.r, lora_alpha=a.alpha, lora_dropout=0.05, task_type="CAUSAL_LM",
                                             target_modules=targets))
    model.print_trainable_parameters()
    tr = [e for e in (encode(tok, x, a.max_len) for x in read("sft_train.jsonl")) if e]
    dv = [e for e in (encode(tok, x, a.max_len) for x in read("sft_dev.jsonl")) if e]
    print(f"train {len(tr)} / dev {len(dv)} examples (longer than --max-len skipped)")
    args = TrainingArguments(
        output_dir=a.out, num_train_epochs=a.epochs, learning_rate=a.lr, per_device_train_batch_size=1,
        per_device_eval_batch_size=1, gradient_accumulation_steps=a.grad_accum, lr_scheduler_type="linear",
        warmup_steps=max(1, math.ceil(0.03 * a.epochs * len(tr) / a.grad_accum)), logging_steps=5, eval_strategy="steps", eval_steps=a.save_steps, save_steps=a.save_steps,
        save_total_limit=3, load_best_model_at_end=True, metric_for_best_model="eval_loss", fp16=not a.no_4bit,
        optim="paged_adamw_8bit" if not a.no_4bit else "adamw_torch", gradient_checkpointing=not a.no_4bit,
        report_to=[], seed=a.seed, remove_unused_columns=False)
    trainer = Trainer(model=model, args=args, train_dataset=tr, eval_dataset=dv,
                      data_collator=DataCollatorForSeq2Seq(tok, padding=True, label_pad_token_id=-100))
    last = max(Path(a.out).glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[1]), default=None) if Path(a.out).exists() else None
    trainer.train(resume_from_checkpoint=str(last) if last else None)
    final = Path(a.out) / "adapter"
    trainer.model.save_pretrained(final)
    tok.save_pretrained(final)
    meta = {"base": a.base, "revision": a.revision, "args": vars(a), "lora_targets": targets, "n_train": len(tr), "n_dev": len(dv),
            "data_manifest": json.loads((DATA / "manifest.json").read_text())["files"],
            "log_history": trainer.state.log_history,
            "steps": trainer.state.global_step, "best_checkpoint": trainer.state.best_model_checkpoint,
            "expected_steps": math.ceil(len(tr) / a.grad_accum) * a.epochs}
    (Path(a.out) / "train_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({"adapter": str(final), "steps": meta["steps"], "best": meta["best_checkpoint"]}))


if __name__ == "__main__":
    main()
