"""Feasibility estimate for soft prompt training/evaluation of Qwen3-4B-Instruct-2507, from the model config, the
measured token lengths of the SFT data and a MEASURED matmul throughput of this machine. Loads no model weights, so
it is allowed in compute window 0 (run under nice -n 19).

  nice -n 19 python -m prompt_tuning.estimate --tokenizer <dir with Qwen3 tokenizer> [--out ...json]

Model FLOPs: forward ~ 2 * N_params * tokens (+ attention, small at <= 700 tokens); prompt tuning needs the full
backward through every layer (the gradient must reach the input embeddings), backward ~ 2 x forward, so training ~
3 x forward. Weight-gradient GEMMs are skipped for frozen weights (~ -1/3 of backward); not credited here, so the
estimate is conservative by up to ~25 %. The measured GEMM rate is an upper bound for real transformer throughput.
"""
import argparse
import json
import os
import time
from pathlib import Path

from .common import RESULTS, SFT_TRAIN, SFT_VAL, read_jsonl

QWEN3_4B = {"hidden_size": 2560, "intermediate_size": 9728, "num_hidden_layers": 36, "num_attention_heads": 32,
            "num_key_value_heads": 8, "head_dim": 128, "vocab_size": 151936, "tie_word_embeddings": True}


def n_params(c):
    h, i, L, v = c["hidden_size"], c["intermediate_size"], c["num_hidden_layers"], c["vocab_size"]
    q = c["num_attention_heads"] * c["head_dim"]
    kv = c["num_key_value_heads"] * c["head_dim"]
    per_layer = h * q + 2 * h * kv + q * h + 3 * h * i + 2 * h + 2 * c["head_dim"]
    emb = v * h
    return {"total": L * per_layer + emb * (1 if c["tie_word_embeddings"] else 2) + h,
            "non_embedding": L * per_layer, "embedding": emb}


def gemm_gflops(dtype_name, n=2048, reps=5):
    import torch

    dt = getattr(torch, dtype_name)
    a, b = torch.randn(n, n, dtype=dt), torch.randn(n, n, dtype=dt)
    a @ b
    t0 = time.perf_counter()
    for _ in range(reps):
        a @ b
    return 2 * n ** 3 * reps / (time.perf_counter() - t0) / 1e9


def token_stats(tok, path, n_virtual):
    from finetune.train_lora import encode

    lens = [len(e["input_ids"]) + n_virtual for e in (encode(tok, ex, 10 ** 6) for ex in read_jsonl(path))]
    lens.sort()
    return {"n": len(lens), "mean": sum(lens) / len(lens), "max": lens[-1], "total": sum(lens)}


def estimate(cfg, train_tok, val_tok, gflops, epochs, n_virtual, gpu_tflops):
    p = n_params(cfg)
    fwd_per_token = 2 * p["non_embedding"] + 2 * p["embedding"]  # lm_head GEMM counts, embedding lookup does not
    train_flops = 3 * fwd_per_token * train_tok["total"] * epochs
    val_loss_flops = fwd_per_token * val_tok["total"] * epochs  # one val pass per epoch
    gen_tokens = 60  # mean target 47 tokens + stop; greedy decode is memory-bound, see below
    out = {"params": p, "soft_prompt_params": n_virtual * cfg["hidden_size"],
           "train_tokens_per_epoch": train_tok["total"], "epochs": epochs,
           "train_pflop": round((train_flops + val_loss_flops) / 1e15, 2)}
    sec = (train_flops + val_loss_flops) / (gflops * 1e9)
    out["cpu_train_hours_at_measured_gemm_rate"] = round(sec / 3600, 1)
    out["gpu_train_hours"] = {f"{t}_tflops_effective": round((train_flops + val_loss_flops) / (t * 1e12) / 3600, 2)
                              for t in gpu_tflops}
    w = p["total"]
    out["memory_gb"] = {
        "weights_fp32": round(4 * w / 1e9, 1), "weights_bf16_fp16": round(2 * w / 1e9, 1),
        "logits_fp32_one_example_max_len": round(4 * train_tok["max"] * cfg["vocab_size"] / 1e9, 2),
        # activations kept for backward without checkpointing: ~ L * T * (34 h + 5 a T) bytes in 16-bit (Korthikanti
        # et al. 2022, per sequence); with gradient checkpointing only the L layer inputs (2 * T * h bytes each)
        "activations_16bit_no_ckpt": round(cfg["num_hidden_layers"] * train_tok["max"] * (
            34 * cfg["hidden_size"] + 5 * cfg["num_attention_heads"] * train_tok["max"]) / 1e9, 2),
        "activations_16bit_grad_ckpt": round(cfg["num_hidden_layers"] * 2 * train_tok["max"] * cfg["hidden_size"] / 1e9, 3),
    }
    # decode: every new token reads all weights once -> memory bound; prefill: compute bound
    prefill_s = fwd_per_token * val_tok["mean"] / (gflops * 1e9)
    out["cpu_eval"] = {"prefill_s_per_req": round(prefill_s, 1), "gen_tokens_assumed": gen_tokens,
                       "note": "decode is memory-bandwidth bound: bf16 weights 8 GB per token; at ~10-20 GB/s "
                               "effective on 4 vCPU that is ~0.4-0.8 s/token"}
    lo, hi = prefill_s + gen_tokens * 0.4, prefill_s + gen_tokens * 0.8
    out["cpu_eval"]["s_per_req_range"] = [round(lo), round(hi)]
    out["cpu_eval"]["hours_per_arm_202_range"] = [round(lo * 202 / 3600, 1), round(hi * 202 / 3600, 1)]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tokenizer", required=True, help="dir or HF id of the Qwen3-4B-Instruct-2507 tokenizer (no weights)")
    ap.add_argument("--revision")
    ap.add_argument("--epochs", type=float, default=3.0)
    ap.add_argument("--num-virtual-tokens", type=int, default=32)
    ap.add_argument("--out", default=str(RESULTS / "feasibility.json"))
    a = ap.parse_args(argv)
    import torch
    from transformers import AutoTokenizer

    torch.set_num_threads(os.cpu_count() or 1)
    tok = AutoTokenizer.from_pretrained(a.tokenizer, revision=a.revision)
    tr, va = token_stats(tok, SFT_TRAIN, a.num_virtual_tokens), token_stats(tok, SFT_VAL, a.num_virtual_tokens)
    rates = {d: round(gemm_gflops(d), 1) for d in ("float32", "bfloat16")}
    best = max(rates.values())
    res = {"measured": {"gemm_gflops_2048": rates, "cpu_count": os.cpu_count(), "torch": torch.__version__,
                        "train_tokens": tr, "val_tokens": va},
           "estimate": estimate(QWEN3_4B, tr, va, best, a.epochs, a.num_virtual_tokens, gpu_tflops=(8, 20)),
           "label": "ESTIMATE (measured GEMM rate + token counts; no 4B model was loaded)"}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2) + "\n")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
