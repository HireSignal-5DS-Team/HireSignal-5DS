"""Train a soft prompt (PEFT prompt tuning) for the Matcher on finetune/data/sft_train.jsonl. The backbone is frozen;
only the [num_virtual_tokens, hidden_size] virtual-token embeddings are learned.

Loss on assistant tokens only (prompt and virtual tokens are -100). The prompt is rendered exactly as at inference
(chat template, add_generation_prompt=True, enable_thinking=False; same encode() as finetune/train_lora.py).
Selection: the checkpoint with the lowest val loss on finetune/data/sft_val.jsonl is kept as soft_prompt/
(--select-on last keeps the final step instead). Val loss is the only use of val; the locked test split is never read.
Re-running the same command resumes from the latest checkpoint; a finished run is left untouched.

  # GPU (Kaggle T4): base arm
  python -m prompt_tuning.train_soft_prompt --run-id sp-base-v1 --device cuda --dtype float16
  # on top of the frozen, merged Matcher LoRA
  python -m prompt_tuning.train_soft_prompt --run-id sp-lora-v1 --lora HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora \\
      --lora-revision 0b6925b1e3c89b6b266b10bcd30af4c6a0c2dc3a --device cuda --dtype float16
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

from .common import (BASE, BASE_REVISION, INIT_TEXT, MANIFEST, ROOT, SFT_TRAIN, SFT_VAL, check_no_leakage,
                     config_hash, held_out_ids, read_jsonl, sha256)

CPU_PARAM_LIMIT = 200_000_000  # above this, CPU training is refused unless --allow-large-cpu (see README feasibility)
NON_RESULT_ARGS = ("max_steps", "epochs", "device", "save_every", "keep_checkpoints", "log_every", "eval_every",
                   "allow_large_cpu", "eval_limit")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--revision", default=BASE_REVISION)
    ap.add_argument("--lora", default=None, help="train on top of this LoRA, merged and frozen (arm lora_soft_prompt)")
    ap.add_argument("--lora-revision", default=None)
    ap.add_argument("--train", default=str(SFT_TRAIN))
    ap.add_argument("--val", default=str(SFT_VAL), help="val loss for checkpoint selection only; '' to skip")
    ap.add_argument("--manifest", default=str(MANIFEST), help="held-out case_ids (val + locked test) for the leak check")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--runs-dir", default=str(ROOT / "prompt_tuning/runs"))
    ap.add_argument("--num-virtual-tokens", type=int, default=32)
    ap.add_argument("--init", default="text", choices=["text", "random"])
    ap.add_argument("--init-text", default=INIT_TEXT)
    ap.add_argument("--epochs", type=float, default=3.0)
    ap.add_argument("--max-steps", type=int, default=0, help="optimizer steps; overrides --epochs when > 0")
    ap.add_argument("--lr", type=float, default=3e-2)
    ap.add_argument("--warmup-ratio", type=float, default=0.06)
    ap.add_argument("--weight-decay", type=float, default=0.0)
    ap.add_argument("--grad-accum", type=int, default=16)
    ap.add_argument("--max-len", type=int, default=2048, help="examples longer than this are skipped, never truncated")
    ap.add_argument("--save-every", type=int, default=10)
    ap.add_argument("--eval-every", type=int, default=0, help="val loss every N steps (0 = once per epoch)")
    ap.add_argument("--eval-limit", type=int, default=0, help="first N val examples for the loss (0 = all 202)")
    ap.add_argument("--select-on", default="val", choices=["val", "last"])
    ap.add_argument("--keep-checkpoints", type=int, default=2)
    ap.add_argument("--log-every", type=int, default=1)
    ap.add_argument("--grad-ckpt", action="store_true", help="gradient checkpointing (needed for 4B on a 16 GB GPU)")
    ap.add_argument("--dtype", default="float32", choices=["float32", "bfloat16", "float16"],
                    help="dtype of the FROZEN backbone; the soft prompt itself is always float32. float16 uses a "
                         "GradScaler (T4/P100 have no bf16)")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--allow-large-cpu", action="store_true", help="permit a > 200M-param backbone on CPU (days, see README)")
    a = ap.parse_args(argv)
    a.revision = a.revision or None  # '' = local model dir, no revision
    a.argv = list(sys.argv[1:] if argv is None else argv)
    return a


def result_config(a):
    return {k: v for k, v in vars(a).items() if k not in ("runs_dir", "argv", *NON_RESULT_ARGS)}


def environment(torch):
    import peft
    import transformers

    env = {"python": sys.version.split()[0], "platform": platform.platform(), "cpu_count": os.cpu_count(),
           "torch": torch.__version__, "transformers": transformers.__version__, "peft": peft.__version__,
           "cuda": torch.cuda.is_available()}
    if env["cuda"]:
        env["gpu"] = torch.cuda.get_device_name(0)
    return env


def latest_checkpoint(run_dir):
    cks = sorted(run_dir.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[1]))
    cks = [c for c in cks if (c / "state.json").exists()]
    return cks[-1] if cks else None


def eval_loss(pm, data, pad_id, torch, device):
    from finetune.train_lora import collate

    if not data:
        return None
    pm.eval()
    tot, n = 0.0, 0
    with torch.no_grad():
        for ex in data:
            b = {k: v.to(device) for k, v in collate([ex], pad_id, torch).items()}
            k = int((b["labels"][:, 1:] != -100).sum())
            tot, n = tot + pm(**b).loss.float().item() * k, n + k
    pm.train()
    return tot / n


def train(a):
    import torch
    from transformers import get_linear_schedule_with_warmup, set_seed

    from finetune.train_lora import collate, encode

    from . import model as M

    run_dir = Path(a.runs_dir) / a.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    cfg = result_config(a)
    args_path = run_dir / "training_args.json"
    if args_path.exists():
        prev = json.loads(args_path.read_text())
        diff = {k: (prev.get(k), v) for k, v in cfg.items() if prev.get(k) != v}
        if diff:
            raise SystemExit(f"run {a.run_id} exists with different args {diff}; use a new --run-id")
    args_path.write_text(json.dumps(cfg, indent=2) + "\n")

    raw = read_jsonl(a.train)
    val_ids, test_ids = held_out_ids(a.manifest)
    check_no_leakage(raw, val_ids, test_ids, a.train)
    val_raw = read_jsonl(a.val)[: a.eval_limit or None] if a.val else []
    if val_raw and not {r["case_id"] for r in val_raw} <= val_ids:
        raise SystemExit("--val must contain val cases only (it is used for selection, never for gradients)")

    set_seed(a.seed)
    device = a.device if a.device != "auto" else ("cuda" if torch.cuda.is_available() else "cpu")
    if device == "cpu":
        torch.set_num_threads(os.cpu_count() or 1)
    backbone, tok, prov = M.load_backbone(a.base, a.revision, a.lora, a.lora_revision, a.dtype, "cpu")
    if device == "cpu" and prov["n_params"] > CPU_PARAM_LIMIT and not a.allow_large_cpu:
        raise SystemExit(f"backbone has {prov['n_params']:,} params; CPU training is infeasible here "
                         f"(see prompt_tuning/README.md, feasibility). Use the Kaggle GPU notebook.")
    pad_id = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    data = [e for e in (encode(tok, ex, a.max_len) for ex in raw) if e]
    val = [e for e in (encode(tok, ex, a.max_len) for ex in val_raw) if e]
    if not data:
        raise SystemExit("no training example fits --max-len")
    steps_per_epoch = math.ceil(len(data) / a.grad_accum)
    total = a.max_steps or max(1, math.ceil(steps_per_epoch * a.epochs))
    eval_every = a.eval_every or steps_per_epoch
    rng, order = random.Random(a.seed), []
    while len(order) < total * a.grad_accum:
        perm = list(range(len(data)))
        rng.shuffle(perm)
        order += perm

    if a.grad_ckpt:
        backbone.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        backbone.config.use_cache = False
    ck = latest_checkpoint(run_dir)
    if ck:
        pm = M.load_soft_prompt(backbone, ck / "soft_prompt", prov, trainable_=True)
    else:
        pm = M.new_soft_prompt(backbone, a.base, a.revision, a.num_virtual_tokens, a.init, a.init_text)
    pm.prompt_encoder["default"].float()
    pm.to(device).train()
    params = M.trainable(pm)
    n_train = sum(p.numel() for p in params)
    assert n_train == a.num_virtual_tokens * backbone.config.hidden_size, (n_train, "only the soft prompt may train")
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=a.weight_decay)
    sched = get_linear_schedule_with_warmup(opt, int(a.warmup_ratio * total), total)
    scaler = torch.amp.GradScaler(device, enabled=(a.dtype == "float16"))
    step, best = 0, {"val_loss": None, "step": None}
    if ck:
        st = torch.load(ck / "trainer.pt", weights_only=False)
        opt.load_state_dict(st["optimizer"])
        sched.load_state_dict(st["scheduler"])
        scaler.load_state_dict(st["scaler"])
        torch.set_rng_state(st["torch_rng"])
        random.setstate(st["py_rng"])
        state = json.loads((ck / "state.json").read_text())
        step, best = state["global_step"], state["best"]
        print(f"resuming from {ck} at step {step}")

    log_path = run_dir / "loss_log.jsonl"
    if step >= total and (run_dir / "soft_prompt/adapter_config.json").exists():
        print(f"run {a.run_id} already finished ({step}/{total} steps); nothing to do")
        return run_dir
    print(f"backbone={a.base}{' + ' + a.lora + ' (merged)' if a.lora else ''} params={prov['n_params']:,} "
          f"trainable={n_train:,} examples={len(data)} skipped_too_long={len(raw) - len(data)} steps={total} "
          f"device={device} dtype={a.dtype}", flush=True)
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()

    t0 = time.perf_counter()
    while step < total:
        loss_sum, tok_sum = 0.0, 0
        for j in range(a.grad_accum):
            ex = data[order[step * a.grad_accum + j]]
            b = {k: v.to(device) for k, v in collate([ex], pad_id, torch).items()}
            n_tok = int((b["labels"][:, 1:] != -100).sum())
            loss = pm(**b).loss.float()
            scaler.scale(loss / a.grad_accum).backward()
            loss_sum, tok_sum = loss_sum + loss.item() * n_tok, tok_sum + n_tok
        scaler.unscale_(opt)
        gn = float(torch.nn.utils.clip_grad_norm_(params, 1.0))
        scaler.step(opt)
        scaler.update()
        sched.step()
        opt.zero_grad(set_to_none=True)
        step += 1
        rec = {"step": step, "loss": loss_sum / max(tok_sum, 1), "grad_norm": gn, "lr": sched.get_last_lr()[0],
               "epoch": round(step / steps_per_epoch, 3), "elapsed_s": round(time.perf_counter() - t0, 2)}
        if not math.isfinite(rec["loss"]):
            raise FloatingPointError(f"non-finite loss at step {step}: {rec['loss']}")
        if step % eval_every == 0 or step == total:
            rec["val_loss"] = eval_loss(pm, val, pad_id, torch, device)
            if rec["val_loss"] is not None and (best["val_loss"] is None or rec["val_loss"] < best["val_loss"]):
                best = {"val_loss": rec["val_loss"], "step": step}
                M.save_soft_prompt(pm, run_dir / "best", prov, {"step": step, "val_loss": rec["val_loss"]})
        if device == "cuda":
            rec["peak_vram_mb"] = round(torch.cuda.max_memory_allocated() / 2**20, 1)
        if step % a.log_every == 0 or step == total or "val_loss" in rec:
            with log_path.open("a") as f:
                f.write(json.dumps(rec) + "\n")
            print(json.dumps(rec), flush=True)
        if step % a.save_every == 0 or step == total:
            save_checkpoint(run_dir, step, pm, prov, opt, sched, scaler, best, torch, a.keep_checkpoints)

    finalize(run_dir, a, pm, tok, prov, n_train, len(data), len(raw) - len(data), total, best, environment(torch))
    return run_dir


def save_checkpoint(run_dir, step, pm, prov, opt, sched, scaler, best, torch, keep):
    from . import model as M

    ck = run_dir / f"checkpoint-{step}"
    M.save_soft_prompt(pm, ck / "soft_prompt", prov)
    torch.save({"optimizer": opt.state_dict(), "scheduler": sched.state_dict(), "scaler": scaler.state_dict(),
                "torch_rng": torch.get_rng_state(), "py_rng": random.getstate()}, ck / "trainer.pt")
    (ck / "state.json").write_text(json.dumps({"global_step": step, "best": best}) + "\n")  # last: complete save
    for old in sorted(run_dir.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[1]))[:-keep]:
        shutil.rmtree(old)


def finalize(run_dir, a, pm, tok, prov, n_train, n_ex, n_skip, total, best, env):
    from . import model as M

    out = run_dir / "soft_prompt"
    cfg = result_config(a)
    chash = config_hash(cfg)
    if a.select_on == "val" and best["step"] is not None:
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(run_dir / "best", out)
        side = json.loads((out / M.SIDE_FILE).read_text())
    else:
        M.save_soft_prompt(pm, out, prov, {"step": total})
        side = json.loads((out / M.SIDE_FILE).read_text())
    side.update(train_config_hash=chash, selected_step=best["step"] if a.select_on == "val" else total,
                selected_val_loss=best["val_loss"] if a.select_on == "val" else None, select_on=a.select_on)
    (out / M.SIDE_FILE).write_text(json.dumps(side, indent=2) + "\n")
    tok.save_pretrained(out)
    provenance = {"backbone": prov, "trainable_params": n_train, "num_virtual_tokens": a.num_virtual_tokens,
                  "init": a.init, "init_text": a.init_text if a.init == "text" else None,
                  "train_file": str(Path(a.train).resolve()), "train_sha256": sha256(a.train),
                  "val_file": str(Path(a.val).resolve()) if a.val else None, "val_sha256": sha256(a.val) if a.val else None,
                  "manifest_sha256": sha256(a.manifest), "n_train_examples": n_ex, "n_skipped_too_long": n_skip,
                  "optimizer_steps": total, "selected": {"on": a.select_on, **best}, "train_config_hash": chash,
                  "soft_prompt_sha256": sha256(out / "soft_prompt.safetensors")}
    (run_dir / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    (run_dir / "environment.json").write_text(json.dumps(env, indent=2) + "\n")
    cmd = " ".join(["python -m prompt_tuning.train_soft_prompt", *a.argv])
    (run_dir / "README.md").write_text(
        f"# Soft prompt run `{a.run_id}` (EXPERIMENTAL)\n\nBackbone: `{a.base}` @ `{a.revision}`"
        f"{f' + LoRA `{a.lora}` @ `{a.lora_revision}` (merged, frozen)' if a.lora else ''}, dtype {a.dtype}.\n"
        f"Soft prompt: {a.num_virtual_tokens} virtual tokens ({n_train:,} trainable params), init {a.init}; "
        f"{total} optimizer steps, lr {a.lr}, grad-accum {a.grad_accum}. Selected step {side['selected_step']} "
        f"(on {a.select_on}, val loss {best['val_loss']}). Config hash `{chash}`.\n\n"
        f"Reproduce:\n\n```\n{cmd}\n```\n\nA low loss is not a result: evaluate with `prompt_tuning.evaluate`.\n")


if __name__ == "__main__":
    train(parse_args())
