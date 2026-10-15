# finetune/ — LoRA SFT for the Matcher SLM

Trains a LoRA adapter for the ONE generative model of the Matcher (< 1B params, default
`Qwen/Qwen2.5-0.5B-Instruct`). Training uses exactly the inference prompt: `matcher.prompt.messages()` for the
input and `matcher.prompt.target(ModelAnswer)` for the output, rendered with the same
`apply_chat_template(..., add_generation_prompt=True, enable_thinking=False)` call as `TransformersBackend`.

Data rules (see `benchmark/CONTRACT.md`): training reads `benchmark/data/train.jsonl` only. `val.jsonl` is for model
selection; `test.jsonl` is locked. `build_sft.py` refuses any input whose file name contains `test` or `val`, and any
case whose `split` is not `train`. `train_lora.py` refuses data files named `*test*`.

## Files

| file | what |
|---|---|
| `build_sft.py` | train.jsonl -> `data/sft_train.jsonl` + `data/sft_dev.jsonl` (10% of cases by sha256(case_id)) + `data/sft_meta.json` |
| `train_lora.py` | LoRA training loop (PyTorch + transformers + PEFT), CPU or CUDA, resumable |
| `configs/qwen25_05b.yaml` | r=16, alpha=32, dropout=0.05, all attn+MLP proj, lr 2e-4, max_len 1024, batch 1 x grad_accum 8, seed 13 |
| `configs/tiny_test.yaml` | 2.4M-param random Qwen2, plumbing only |
| `tests/` | `pytest -q finetune` (downloads a 4 MB tiny model once) |

Gold data has no explanation text, so `build_sft.py` writes a short deterministic one from decision/basis/evidence.
Knowledge refs come from `RagKnowledge` (BM25 over ESCO, offline, k=3 — same as `Matcher`). `--knowledge none`
uses `NoKnowledge`; only use it if inference also runs without RAG, otherwise train and inference prompts differ.

## Steps

```bash
# 1. SFT data (seconds)
python -m finetune.build_sft benchmark/data/train.jsonl            # -> finetune/data/

# 2. Token lengths (no training; examples over max_len are skipped, never truncated)
python -m finetune.train_lora --config finetune/configs/qwen25_05b.yaml --stats-only

# 3a. CPU pilot (5 steps, measure sec/step and RSS)
python -m finetune.train_lora --config finetune/configs/qwen25_05b.yaml --name pilot --max-steps 5 --grad-accum 1 --threads 4

# 3b. Full run (same command on CPU or GPU; device=auto picks CUDA + bf16 when available)
python -m finetune.train_lora --config finetune/configs/qwen25_05b.yaml --name qwen25_05b_lora
```

Interrupted? Re-run the same command: it resumes from the latest `runs/<name>/checkpoint-<step>/`
(adapter + optimizer + scheduler + data position). Pass `--max-steps` / `--epochs` to override the config.

Outputs in `finetune/runs/<name>/`: `checkpoint-<step>/`, `best/` (lowest dev loss), `final/`, `log.jsonl`
(train loss, lr, sec/step, peak RSS; dev loss every `eval_every` steps), `run_config.json` (config, versions,
param counts, sha256 of train/dev SFT files, length distribution, skipped counts). Early stopping: `early_stopping_patience`
dev evaluations without improvement.

## Use the adapter

```python
from matcher.backends import TransformersBackend
be = TransformersBackend("Qwen/Qwen2.5-0.5B-Instruct", adapter_id="finetune/runs/qwen25_05b_lora/best")
```
`check_adapter_compat` passes because `adapter_config.json` records the same base id. Select the checkpoint on
`val.jsonl` with the benchmark, never on test.

## Resources (measured)

Qwen2.5-0.5B-Instruct, fp32, LoRA r=16 on all 7 projections (8.8M trainable of 494M), batch 1, 4 CPU threads
on a shared 4-core VM, transformers 5.19 / torch 2.14 / peft 0.21:

| seq len (tokens) | gradient_checkpointing | sec per example | peak RSS |
|---|---|---|---|
| ~420 | false | ~5.9 | 6.2 GB |
| ~870 | false | ~12.5 | 9.5 GB |
| ~870 | true | ~16 | 5.2 GB |

One optimizer step = `grad_accum` examples (8 by default). CPU cost of a full run ≈ examples x epochs x sec/example:
e.g. 1,000 examples x 2 epochs x ~12 s ≈ 6.7 h. Turn on `gradient_checkpointing: true` on machines with < 16 GB RAM.
Adapter: 34 MB.

GPU (Kaggle T4/P100, Colab T4, laptop RTX): no config change. `device: auto` uses CUDA, with bf16 where supported
(Ampere+) and fp32 otherwise (T4/P100 have no bf16; fp16 training is not supported here).
Expect roughly 0.2–0.5 s per example at ~1k tokens, i.e. minutes for 1–2k examples. Install:
`pip install torch transformers peft pyyaml safetensors` and copy `matcher/`, `rag/` (for build_sft) and `finetune/`.
