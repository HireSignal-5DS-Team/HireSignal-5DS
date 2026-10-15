"""LoRA SFT for the Matcher SLM (< 1B params). Plain PyTorch + transformers + PEFT; CPU or CUDA.

Loss is on completion tokens only: prompt = tok.apply_chat_template(messages, add_generation_prompt=True,
enable_thinking=False) -- the exact string TransformersBackend.generate builds -- and labels = -100 there.
Examples longer than max_len are skipped (never truncated) and counted.

    python -m finetune.train_lora --config finetune/configs/qwen25_05b.yaml [--max-steps 5] [--name pilot]
    python -m finetune.train_lora --config ... --stats-only     # token-length distribution, no training

Outputs in <output_root>/<name>/: checkpoint-<step>/ (adapter + trainer_state.pt), best/ (lowest dev loss),
final/, log.jsonl, run_config.json. Re-running the same command resumes from the latest checkpoint.
"""
import argparse
import hashlib
import json
import math
import platform
import random
import resource
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from matcher.backends import MAX_PARAMS  # noqa: E402
from matcher.prompt import PROMPT_VERSION  # noqa: E402

DEFAULTS = {
    "name": "lora", "base_model": None, "revision": None,
    "train_file": "finetune/data/sft_train.jsonl", "dev_file": "finetune/data/sft_dev.jsonl",
    "output_root": "finetune/runs",
    "r": 16, "alpha": 32, "dropout": 0.05,
    "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    "lr": 2e-4, "weight_decay": 0.0, "warmup_ratio": 0.05, "epochs": 2, "max_steps": None,
    "max_len": 1024, "batch_size": 1, "grad_accum": 8, "max_grad_norm": 1.0, "seed": 13,
    "save_every": 50, "eval_every": 50, "log_every": 1, "early_stopping_patience": None, "max_dev_examples": None,
    "num_threads": None, "device": "auto", "dtype": "auto", "gradient_checkpointing": False,
    "chat_kwargs": {"enable_thinking": False},
}


def load_config(path, overrides):
    cfg = dict(DEFAULTS)
    if path:
        text = Path(path).read_text()
        if str(path).endswith((".yaml", ".yml")):
            import yaml
            cfg.update(yaml.safe_load(text) or {})
        else:
            cfg.update(json.loads(text))
    cfg.update({k: v for k, v in overrides.items() if v is not None})
    unknown = set(cfg) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown config keys: {sorted(unknown)}")
    if not cfg["base_model"]:
        raise ValueError("base_model is required")
    for key in ("train_file", "dev_file"):
        if cfg[key] and "test" in Path(cfg[key]).name.lower():
            raise ValueError(f"refusing {key}={cfg[key]}: test data is locked")
    return cfg


def _path(p):
    p = Path(p)
    return p if p.is_absolute() else ROOT / p


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def peak_rss_mb():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)  # Linux: KiB


def encode(tok, example, max_len, chat_kwargs):
    """-> (input_ids, labels) or None if longer than max_len. Prompt tokens are labelled -100."""
    text = tok.apply_chat_template(example["messages"], tokenize=False, add_generation_prompt=True, **chat_kwargs)
    p = tok(text, add_special_tokens=False)["input_ids"]
    c = tok(example["completion"] + tok.eos_token, add_special_tokens=False)["input_ids"]
    if len(p) + len(c) > max_len:
        return None
    return p + c, [-100] * len(p) + c


def load_examples(tok, path, max_len, chat_kwargs):
    rows = [json.loads(line) for line in _path(path).read_text().splitlines() if line.strip()]
    enc, lengths, skipped = [], [], 0
    for r in rows:
        e = encode(tok, r, 10 ** 9, chat_kwargs)
        lengths.append(len(e[0]))
        if len(e[0]) > max_len:
            skipped += 1
        else:
            enc.append(e)
    return enc, lengths, skipped


def length_stats(lengths):
    if not lengths:
        return {}
    s = sorted(lengths)
    q = lambda f: s[min(len(s) - 1, int(f * len(s)))]  # noqa: E731
    return {"n": len(s), "min": s[0], "p50": q(0.5), "p90": q(0.9), "p99": q(0.99), "max": s[-1],
            "mean": round(sum(s) / len(s), 1)}


def collate(batch, pad_id, device):
    import torch

    n = max(len(ids) for ids, _ in batch)
    ids = torch.full((len(batch), n), pad_id, dtype=torch.long)
    labels = torch.full((len(batch), n), -100, dtype=torch.long)
    mask = torch.zeros((len(batch), n), dtype=torch.long)
    for i, (x, y) in enumerate(batch):
        ids[i, : len(x)], labels[i, : len(y)], mask[i, : len(x)] = torch.tensor(x), torch.tensor(y), 1
    return {"input_ids": ids.to(device), "labels": labels.to(device), "attention_mask": mask.to(device)}


def dev_loss(model, data, cfg, pad_id, device):
    """Token-weighted mean completion loss."""
    import torch

    model.eval()
    tot, n = 0.0, 0
    with torch.no_grad():
        for i in range(0, len(data), cfg["batch_size"]):
            b = collate(data[i: i + cfg["batch_size"]], pad_id, device)
            k = int((b["labels"][:, 1:] != -100).sum())
            tot += float(model(**b).loss) * k
            n += k
    model.train()
    return tot / max(n, 1)


def latest_checkpoint(run_dir):
    cks = sorted(run_dir.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[1]))
    return cks[-1] if cks and (cks[-1] / "trainer_state.pt").exists() else None


def pick_device(name):
    import torch

    return ("cuda" if torch.cuda.is_available() else "cpu") if name == "auto" else name


def pick_dtype(name, device):
    import torch

    if name == "auto":
        return torch.bfloat16 if device == "cuda" and torch.cuda.is_bf16_supported() else torch.float32
    return getattr(torch, name)


def train(cfg, stats_only=False):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, get_linear_schedule_with_warmup

    if cfg["num_threads"]:
        torch.set_num_threads(int(cfg["num_threads"]))
    random.seed(cfg["seed"])
    torch.manual_seed(cfg["seed"])
    device = pick_device(cfg["device"])
    run_dir = _path(cfg["output_root"]) / cfg["name"]

    tok = AutoTokenizer.from_pretrained(cfg["base_model"], revision=cfg["revision"])
    pad_id = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    train_data, train_lens, train_skipped = load_examples(tok, cfg["train_file"], cfg["max_len"], cfg["chat_kwargs"])
    dev_data, dev_lens, dev_skipped = ([], [], 0)
    if cfg["dev_file"] and _path(cfg["dev_file"]).exists():
        dev_data, dev_lens, dev_skipped = load_examples(tok, cfg["dev_file"], cfg["max_len"], cfg["chat_kwargs"])
    if cfg["max_dev_examples"]:
        dev_data = dev_data[: cfg["max_dev_examples"]]
    data_info = {"train_lengths": length_stats(train_lens), "dev_lengths": length_stats(dev_lens),
                 "train_used": len(train_data), "train_skipped_over_max_len": train_skipped,
                 "dev_used": len(dev_data), "dev_skipped_over_max_len": dev_skipped}
    if stats_only:
        return data_info
    if not train_data:
        raise ValueError("no training examples within max_len")

    from peft import LoraConfig, get_peft_model, set_peft_model_state_dict

    model = AutoModelForCausalLM.from_pretrained(cfg["base_model"], revision=cfg["revision"],
                                                 dtype=pick_dtype(cfg["dtype"], device))
    n_params = sum(p.numel() for p in model.parameters())
    if n_params >= MAX_PARAMS:
        raise ValueError(f"{cfg['base_model']} has {n_params:,} parameters; the Matcher requires < 1B")
    if cfg["gradient_checkpointing"]:
        model.gradient_checkpointing_enable()
        model.enable_input_require_grads()
    model = get_peft_model(model, LoraConfig(r=cfg["r"], lora_alpha=cfg["alpha"], lora_dropout=cfg["dropout"],
                                             target_modules=cfg["target_modules"], task_type="CAUSAL_LM"))
    model.to(device).train()
    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)

    micro_per_epoch = math.ceil(len(train_data) / cfg["batch_size"])
    steps_per_epoch = math.ceil(micro_per_epoch / cfg["grad_accum"])
    total_steps = cfg["max_steps"] or steps_per_epoch * cfg["epochs"]
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=cfg["lr"],
                            weight_decay=cfg["weight_decay"])
    sched = get_linear_schedule_with_warmup(opt, int(cfg["warmup_ratio"] * total_steps), total_steps)

    step, best, bad_evals = 0, float("inf"), 0
    ck = latest_checkpoint(run_dir)
    if ck:
        from safetensors.torch import load_file

        set_peft_model_state_dict(model, load_file(str(ck / "adapter_model.safetensors")))
        st = torch.load(ck / "trainer_state.pt", weights_only=False)
        opt.load_state_dict(st["optimizer"])
        sched.load_state_dict(st["scheduler"])
        step, best, bad_evals = st["step"], st["best_dev_loss"], st["bad_evals"]
        torch.set_rng_state(st["torch_rng"])
        print(f"resumed from {ck} at step {step}", flush=True)

    run_dir.mkdir(parents=True, exist_ok=True)
    import peft
    import transformers

    run_config = {"config": cfg, "prompt_version": PROMPT_VERSION, "device": device,
                  "dtype": str(pick_dtype(cfg["dtype"], device)), "n_params": n_params, "n_trainable": n_trainable,
                  "steps_per_epoch": steps_per_epoch, "total_steps": total_steps,
                  "versions": {"python": platform.python_version(), "torch": torch.__version__,
                               "transformers": transformers.__version__, "peft": peft.__version__},
                  "data_sha256": {"train": sha256(_path(cfg["train_file"])),
                                  "dev": sha256(_path(cfg["dev_file"])) if dev_lens else None},
                  "data": data_info, "resumed_from": str(ck) if ck else None}
    (run_dir / "run_config.json").write_text(json.dumps(run_config, indent=2) + "\n")
    log = (run_dir / "log.jsonl").open("a")

    def emit(rec):
        rec = {"step": step, "time": round(time.time(), 1), "peak_rss_mb": peak_rss_mb(), **rec}
        log.write(json.dumps(rec) + "\n")
        log.flush()
        print(json.dumps(rec), flush=True)

    def save(dirname, state=True):
        d = run_dir / dirname
        model.save_pretrained(d)
        tok.save_pretrained(d)
        if state:
            torch.save({"optimizer": opt.state_dict(), "scheduler": sched.state_dict(), "step": step,
                        "best_dev_loss": best, "bad_evals": bad_evals, "torch_rng": torch.get_rng_state()},
                       d / "trainer_state.pt")

    def micro_batches(start_step):
        """Deterministic order: epoch e uses a permutation seeded by seed+e; skip what earlier runs consumed."""
        skip = start_step * cfg["grad_accum"]
        e = 0
        while True:
            order = list(range(len(train_data)))
            random.Random(cfg["seed"] + e).shuffle(order)
            for i in range(0, len(order), cfg["batch_size"]):
                if skip:
                    skip -= 1
                    continue
                yield [train_data[j] for j in order[i: i + cfg["batch_size"]]]
            e += 1

    batches = micro_batches(step)
    stop = False
    while step < total_steps and not stop:
        t0, loss_sum, tokens = time.perf_counter(), 0.0, 0
        for _ in range(cfg["grad_accum"]):
            b = collate(next(batches), pad_id, device)
            loss = model(**b).loss
            (loss / cfg["grad_accum"]).backward()
            loss_sum += float(loss.detach())
            tokens += int(b["attention_mask"].sum())
        torch.nn.utils.clip_grad_norm_(model.parameters(), cfg["max_grad_norm"])
        opt.step()
        sched.step()
        opt.zero_grad(set_to_none=True)
        step += 1
        if step % cfg["log_every"] == 0 or step == total_steps:
            emit({"train_loss": round(loss_sum / cfg["grad_accum"], 4), "lr": sched.get_last_lr()[0],
                  "sec_per_step": round(time.perf_counter() - t0, 2), "tokens": tokens,
                  "epoch": round(step / steps_per_epoch, 3)})
        if dev_data and (step % cfg["eval_every"] == 0 or step == total_steps):
            dl = dev_loss(model, dev_data, cfg, pad_id, device)
            if dl < best:
                best, bad_evals = dl, 0
                save("best", state=False)
            else:
                bad_evals += 1
            emit({"dev_loss": round(dl, 4), "best_dev_loss": round(best, 4)})
            if cfg["early_stopping_patience"] and bad_evals >= cfg["early_stopping_patience"]:
                emit({"early_stop": True})
                stop = True
        if step % cfg["save_every"] == 0 or step == total_steps or stop:
            save(f"checkpoint-{step}")
    save("final", state=False)
    if not dev_data:
        shutil.copytree(run_dir / "final", run_dir / "best", dirs_exist_ok=True)
    log.close()
    return {"run_dir": str(run_dir), "step": step, "best_dev_loss": best, **data_info}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--name")
    ap.add_argument("--base-model", dest="base_model")
    ap.add_argument("--train-file", dest="train_file")
    ap.add_argument("--dev-file", dest="dev_file")
    ap.add_argument("--output-root", dest="output_root")
    ap.add_argument("--max-steps", dest="max_steps", type=int)
    ap.add_argument("--epochs", type=int)
    ap.add_argument("--grad-accum", dest="grad_accum", type=int)
    ap.add_argument("--threads", dest="num_threads", type=int)
    ap.add_argument("--device")
    ap.add_argument("--stats-only", action="store_true", help="print token-length distribution and exit")
    a = vars(ap.parse_args(argv))
    stats_only, config = a.pop("stats_only"), a.pop("config")
    cfg = load_config(config, a)
    print(json.dumps(train(cfg, stats_only=stats_only), indent=2, default=str))


if __name__ == "__main__":
    main()
