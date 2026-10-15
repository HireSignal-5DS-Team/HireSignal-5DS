"""LoRA SFT of the Matcher SLM (< 1B params) on finetune/data/sft_train.jsonl. Plain PyTorch loop, CPU-friendly.

Loss is computed on assistant (target) tokens only; prompt tokens are -100. The prompt is rendered exactly as
TransformersBackend renders it at inference (chat template, add_generation_prompt=True, enable_thinking=False).
Re-running the same command resumes from the latest checkpoint; a finished run is left untouched.

  python -m finetune.train_lora --base Qwen/Qwen2.5-0.5B-Instruct --run-id q25-r16 --epochs 2
"""
import argparse
import json
import math
import os
import platform
import random
import shutil
import sys
import time
from pathlib import Path

from matcher.backends import MAX_PARAMS

ROOT = Path(__file__).resolve().parents[1]
TARGETS = "q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj"


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="HF model id or local dir of the base SLM")
    ap.add_argument("--revision", default=None, help="pin a commit/tag of the base model")
    ap.add_argument("--train", default=str(ROOT / "finetune/data/sft_train.jsonl"))
    ap.add_argument("--val", default=str(ROOT / "finetune/data/sft_val.jsonl"), help="eval loss only; '' to skip")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--runs-dir", default=str(ROOT / "finetune/runs"))
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--max-steps", type=int, default=0, help="optimizer steps; overrides --epochs when > 0")
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--warmup-ratio", type=float, default=0.03)
    ap.add_argument("--weight-decay", type=float, default=0.0)
    ap.add_argument("--batch-size", type=int, default=1, help="micro batch (examples per forward)")
    ap.add_argument("--grad-accum", type=int, default=16)
    ap.add_argument("--max-len", type=int, default=2048, help="examples longer than this are skipped, never truncated")
    ap.add_argument("--r", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=32)
    ap.add_argument("--dropout", type=float, default=0.05)
    ap.add_argument("--target-modules", default=TARGETS)
    ap.add_argument("--save-every", type=int, default=25, help="checkpoint every N optimizer steps")
    ap.add_argument("--keep-checkpoints", type=int, default=2)
    ap.add_argument("--log-every", type=int, default=1)
    ap.add_argument("--grad-ckpt", action="store_true", help="gradient checkpointing (less memory, slower)")
    ap.add_argument("--dtype", default="float32", choices=["float32", "bfloat16", "float16"])
    ap.add_argument("--device", default="auto", help="auto|cpu|cuda|mps")
    ap.add_argument("--seed", type=int, default=13)
    a = ap.parse_args(argv)
    a.argv = list(sys.argv[1:] if argv is None else argv)
    return a


def check_params(n):
    if n >= MAX_PARAMS:
        raise ValueError(f"base has {n:,} parameters; the Matcher requires < 1B, refusing to train")


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def encode(tok, ex, max_len):
    """input_ids/labels with prompt masked; None if longer than max_len (truncating would cut the CV or target)."""
    *msgs, ans = ex["messages"]
    assert ans["role"] == "assistant", "last message must be the assistant target"
    p = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    p_ids = tok(p, add_special_tokens=False)["input_ids"]
    t_ids = tok(ans["content"] + tok.eos_token, add_special_tokens=False)["input_ids"]
    if len(p_ids) + len(t_ids) > max_len:
        return None
    return {"input_ids": p_ids + t_ids, "labels": [-100] * len(p_ids) + t_ids}


def collate(batch, pad_id, torch):
    n = max(len(b["input_ids"]) for b in batch)
    ids = torch.full((len(batch), n), pad_id, dtype=torch.long)
    labels = torch.full((len(batch), n), -100, dtype=torch.long)
    mask = torch.zeros((len(batch), n), dtype=torch.long)
    for i, b in enumerate(batch):
        k = len(b["input_ids"])
        ids[i, :k], labels[i, :k], mask[i, :k] = torch.tensor(b["input_ids"]), torch.tensor(b["labels"]), 1
    return {"input_ids": ids, "labels": labels, "attention_mask": mask}


def latest_checkpoint(run_dir):
    cks = sorted(run_dir.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[1]))
    cks = [c for c in cks if (c / "state.json").exists()]  # a checkpoint without state.json was interrupted mid-save
    return cks[-1] if cks else None


def environment(torch):
    import peft
    import transformers

    env = {"python": sys.version, "platform": platform.platform(), "machine": platform.machine(),
           "cpu_count": os.cpu_count(), "torch": torch.__version__, "transformers": transformers.__version__,
           "peft": peft.__version__, "cuda": torch.cuda.is_available()}
    if env["cuda"]:
        env["gpu"] = torch.cuda.get_device_name(0)
    try:
        env["ram_gb"] = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1)
    except (ValueError, OSError, AttributeError):
        pass
    return env


def eval_loss(model, data, pad_id, torch, device):
    if not data:
        return None
    model.eval()
    tot, n = 0.0, 0
    with torch.no_grad():
        for ex in data:
            b = {k: v.to(device) for k, v in collate([ex], pad_id, torch).items()}
            tok_n = int((b["labels"][:, 1:] != -100).sum())
            tot, n = tot + model(**b).loss.item() * tok_n, n + tok_n
    model.train()
    return tot / n


def train(a):
    import torch
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, get_linear_schedule_with_warmup, set_seed

    from finetune.build_sft import sha256

    run_dir = Path(a.runs_dir) / a.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    args_path = run_dir / "training_args.json"
    cur = {k: v for k, v in vars(a).items() if k not in ("runs_dir", "argv")}
    if args_path.exists():  # resuming: refuse silent changes to anything that alters the result
        prev = json.loads(args_path.read_text())
        diff = {k: (prev.get(k), v) for k, v in cur.items() if k not in ("max_steps", "epochs", "device", "save_every",
                                                                       "keep_checkpoints", "log_every") and prev.get(k) != v}
        if diff:
            raise SystemExit(f"run {a.run_id} exists with different args {diff}; use a new --run-id")
    args_path.write_text(json.dumps(cur, indent=2) + "\n")

    set_seed(a.seed)
    torch.set_num_threads(os.cpu_count() or 1)
    device = a.device if a.device != "auto" else (
        "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")

    tok = AutoTokenizer.from_pretrained(a.base, revision=a.revision)
    pad_id = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    model = AutoModelForCausalLM.from_pretrained(a.base, revision=a.revision, dtype=getattr(torch, a.dtype))
    n_params = sum(p.numel() for p in model.parameters())
    check_params(n_params)
    commit = getattr(model.config, "_commit_hash", None)
    if a.grad_ckpt:
        model.gradient_checkpointing_enable()
        model.enable_input_require_grads()
        model.config.use_cache = False

    raw = read_jsonl(a.train)
    enc = [encode(tok, ex, a.max_len) for ex in raw]
    data = [e for e in enc if e]
    val = [e for e in (encode(tok, ex, a.max_len) for ex in (read_jsonl(a.val) if a.val else [])) if e]
    if not data:
        raise SystemExit("no training example fits --max-len")
    steps_per_epoch = math.ceil(len(data) / (a.batch_size * a.grad_accum))
    total = a.max_steps or max(1, math.ceil(steps_per_epoch * a.epochs))

    # fixed micro-batch order for the whole run, derived from the seed, so a resume replays exactly the same data
    rng, order = random.Random(a.seed), []
    while len(order) < total * a.grad_accum * a.batch_size:
        perm = list(range(len(data)))
        rng.shuffle(perm)
        order += perm

    ck = latest_checkpoint(run_dir)
    if ck:
        model = PeftModel.from_pretrained(model, ck / "adapter", is_trainable=True)
    else:
        lcfg = LoraConfig(r=a.r, lora_alpha=a.alpha, lora_dropout=a.dropout, task_type="CAUSAL_LM",
                          target_modules=a.target_modules.split(","))
        model = get_peft_model(model, lcfg)
    model.to(device).train()
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=a.lr, weight_decay=a.weight_decay)
    sched = get_linear_schedule_with_warmup(opt, int(a.warmup_ratio * total), total)
    step = 0
    if ck:
        st = torch.load(ck / "trainer.pt", weights_only=False)
        opt.load_state_dict(st["optimizer"])
        sched.load_state_dict(st["scheduler"])
        torch.set_rng_state(st["torch_rng"])
        random.setstate(st["py_rng"])
        step = json.loads((ck / "state.json").read_text())["global_step"]
        print(f"resuming from {ck} at step {step}")

    log_path = run_dir / "loss_log.jsonl"
    if step >= total and (run_dir / "adapter/adapter_config.json").exists():
        print(f"run {a.run_id} already finished ({step}/{total} steps); nothing to do")
        return run_dir
    print(f"base={a.base} params={n_params:,} trainable={trainable:,} examples={len(data)} "
          f"skipped_too_long={len(raw) - len(data)} steps={total} device={device}")

    t0, mb = time.perf_counter(), a.batch_size
    while step < total:
        loss_sum, tok_sum = 0.0, 0
        for j in range(a.grad_accum):
            s = (step * a.grad_accum + j) * mb
            b = {k: v.to(device) for k, v in collate([data[i] for i in order[s:s + mb]], pad_id, torch).items()}
            n_tok = int((b["labels"][:, 1:] != -100).sum())
            loss = model(**b).loss
            (loss / a.grad_accum).backward()
            loss_sum, tok_sum = loss_sum + loss.item() * n_tok, tok_sum + n_tok
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
        opt.step()
        sched.step()
        opt.zero_grad(set_to_none=True)
        step += 1
        rec = {"step": step, "loss": loss_sum / max(tok_sum, 1), "lr": sched.get_last_lr()[0],
               "epoch": round(step / steps_per_epoch, 3), "elapsed_s": round(time.perf_counter() - t0, 2)}
        if not math.isfinite(rec["loss"]):
            raise FloatingPointError(f"non-finite loss at step {step}: {rec['loss']}")
        if step % a.log_every == 0 or step == total:
            with log_path.open("a") as f:
                f.write(json.dumps(rec) + "\n")
            print(json.dumps(rec), flush=True)
        if step % a.save_every == 0 or step == total:
            save_checkpoint(run_dir, step, model, opt, sched, torch, a.keep_checkpoints)

    vl = eval_loss(model, val, pad_id, torch, device)
    with log_path.open("a") as f:
        f.write(json.dumps({"step": step, "val_loss": vl, "n_val": len(val)}) + "\n")
    finalize(run_dir, a, model, tok, n_params, trainable, commit, len(data), len(raw) - len(data), total, vl,
             environment(torch), sha256)
    return run_dir


def save_checkpoint(run_dir, step, model, opt, sched, torch, keep):
    ck = run_dir / f"checkpoint-{step}"
    model.save_pretrained(ck / "adapter")
    torch.save({"optimizer": opt.state_dict(), "scheduler": sched.state_dict(), "torch_rng": torch.get_rng_state(),
                "py_rng": random.getstate()}, ck / "trainer.pt")
    (ck / "state.json").write_text(json.dumps({"global_step": step}) + "\n")  # written last: marks a complete save
    for old in sorted(run_dir.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[1]))[:-keep]:
        shutil.rmtree(old)


def finalize(run_dir, a, model, tok, n_params, trainable, commit, n_ex, n_skip, total, val_loss, env, sha256):
    out = run_dir / "adapter"
    model.save_pretrained(out)
    tok.save_pretrained(out)
    meta_path = Path(a.train).with_suffix("").with_suffix(".meta.json")
    prov = {
        "base_model": a.base, "base_revision": a.revision, "base_commit_hash": commit, "base_n_params": n_params,
        "trainable_params": trainable, "train_file": str(Path(a.train).resolve()), "train_sha256": sha256(a.train),
        "val_file": str(Path(a.val).resolve()) if a.val else None, "val_sha256": sha256(a.val) if a.val else None,
        "sft_meta": json.loads(meta_path.read_text()) if meta_path.exists() else None,
        "n_train_examples": n_ex, "n_skipped_too_long": n_skip, "optimizer_steps": total, "final_val_loss": val_loss,
    }
    (run_dir / "provenance.json").write_text(json.dumps(prov, indent=2) + "\n")
    (run_dir / "environment.json").write_text(json.dumps(env, indent=2) + "\n")
    cmd = " ".join(["python -m finetune.train_lora", *a.argv])
    (run_dir / "README.md").write_text(
        f"# LoRA run `{a.run_id}`\n\nBase: `{a.base}` revision `{a.revision}` (commit `{commit}`), {n_params:,} params.\n"
        f"LoRA r={a.r} alpha={a.alpha} dropout={a.dropout} on {a.target_modules}; {total} optimizer steps, "
        f"lr {a.lr}, batch {a.batch_size} x accum {a.grad_accum}. Final val loss: {val_loss}.\n\n"
        f"Files: `adapter/` (weights, adapter_config.json, tokenizer), `training_args.json`, `provenance.json` "
        f"(dataset sha256), `loss_log.jsonl`, `environment.json`.\n\n"
        f"Reproduce (from the repo root, same SFT files - check sha256 in provenance.json):\n\n```\n{cmd}\n```\n\n"
        f"A low training loss is not a result. Compare against the exact base on val with `benchmark.run` "
        f"(see finetune/README.md) before keeping this adapter.\n")


if __name__ == "__main__":
    train(parse_args())
