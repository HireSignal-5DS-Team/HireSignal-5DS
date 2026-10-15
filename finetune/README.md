# LoRA fine-tuning of the Matcher SLM

Status (2026-10-15): **implemented and smoke-tested only.** No HireSignal adapter has been trained.
A full training run waits for approval after the dataset, configuration, resource estimate and
baseline results below have been reviewed.

| Stage | State |
|---|---|
| SFT data builder (`build_sft.py`) | implemented, run on train/val (`finetune/data/`), refuses the locked test split |
| Trainer (`train_lora.py`) | implemented; smoke-tested on a random 2-layer tiny Qwen2 model (`tests/test_smoke.py`) |
| Real training on Qwen2.5-0.5B-Instruct / Qwen3-0.6B | **not run** |
| Adapter vs exact base comparison | procedure below, not run |

## What the smoke test proves (and does not)

`pytest finetune/tests` builds a tiny randomly initialised Qwen2 model (hidden 64, 2 layers, locally trained
tokenizer), trains 2 steps and resumes to 4. It checks: finite loss, checkpoint written, exact resume (steps
1,2 then 3,4, no restart), idempotent re-run, adapter files saved, adapter reloads with PEFT,
`check_adapter_compat` refuses another base, the < 1B guard and inference through `TransformersBackend`.
It says nothing about matching quality.

## Training data (built, not yet used)

`python -m finetune.build_sft --split train --knowledge rag` and `--split val`:

| file | cases | examples (requirements) | MET / MISSING / UNCERTAIN | source sha256 |
|---|---|---|---|---|
| `data/sft_train.jsonl` | 150 | 681 | 305 / 273 / 103 | `d0206264f093…` (benchmark/data/train.jsonl) |
| `data/sft_val.jsonl` (eval loss only) | 45 | 202 | 86 / 77 / 39 | `37c60915f2db…` |

Each example = system + user message from `matcher.prompt` (the exact inference prompt, with the same 3 ESCO
references from BM25) + assistant target `{"decision","basis","evidence","explanation"}`. Gold explanations are
one fixed sentence per decision/basis (the data has no free-text rationales), so the adapter learns the decision,
basis and verbatim quotes, not explanation style.

Token lengths (measured with the real tokenizers): prompt mean 406 / max 601 tokens (Qwen2.5), 410 / 605
(Qwen3); target mean 47 / max 60. Whole train set ≈ 310k tokens per epoch.

## Proposed configuration (to approve)

| parameter | value | why |
|---|---|---|
| base | the best untuned base on val (see `benchmark/results/COMPARISON_val.md`) | train only what is selected |
| LoRA | r=16, alpha=32, dropout=0.05, q/k/v/o/gate/up/down proj | standard for 0.5B models; ≈ 9–10 M trainable params |
| loss | assistant tokens only (prompt masked with -100) | learn the answer, not the CV |
| lr / schedule | 2e-4, linear, 3 % warm-up, grad clip 1.0 | common LoRA defaults |
| batch | 1 × grad-accum 16 | 6 GB VRAM |
| epochs | 2 (≈ 86 optimizer steps) | small dataset; compare val loss each run |
| dtype | bfloat16 on the RTX 4050 (Ada supports bf16), float32 on CPU | no fp16: the loop has no loss scaler |
| checkpoints | every 25 steps, keep 2; resumable | interruption-safe |
| seed | 13 | reproducible order |

Resource estimate (reasoned, not measured): Qwen3-0.6B bf16 weights ≈ 1.2 GB, LoRA params + AdamW states
≈ 0.2 GB, activations for ≤ 670 tokens at batch 1 well under 1 GB → **≈ 2.5–3.5 GB VRAM**, fits 6 GB
(add `--grad-ckpt` if it does not). Time on an RTX 4050: minutes per epoch (≈ 310k tokens). On the 4-core
cloud CPU: roughly one to a few hours for 2 epochs (float32), not attempted.

## Decision rule (pre-registered)

1. Benchmark untuned bases and the existing adapter `Kus-hal/resume-screener-lora` (verified: PEFT LoRA,
   r=16, q/k/v/o, base `Qwen/Qwen2.5-0.5B-Instruct`, MIT; trained for a whole-resume verdict, not our schema) on val.
2. Train a HireSignal adapter only on the selected base, only on train.
3. Keep it only if, against its **exact** untuned base on val, macro-F1 is higher **and** false-MET rate is not
   higher. Then confirm once on the locked test split (`--i-understand-test-is-locked`).

## Commands (Windows RTX 4050 or any machine with huggingface.co access)

```powershell
python -m finetune.build_sft --split train --knowledge rag
python -m finetune.build_sft --split val --knowledge rag
python -m finetune.train_lora --base Qwen/Qwen3-0.6B --revision c1899de289a04d12100db370d81485cdf75e47ca `
    --run-id qwen3-0.6b-r16 --epochs 2 --device cuda --dtype bfloat16
# compare with the exact base on the same val split, same prompt and decoding
python -m benchmark.run --backend transformers --model Qwen/Qwen3-0.6B --revision c1899de289a04d12100db370d81485cdf75e47ca `
    --adapter finetune/runs/qwen3-0.6b-r16/adapter --split val --knowledge rag --device cuda --run-id qwen3-0.6b+hs-lora-rag-val
python -m benchmark.compare --split val
```

Re-running `train_lora` with the same `--run-id` resumes from the last complete checkpoint; changing any
result-affecting argument under the same run id is refused. Each finished run directory holds `adapter/`
(weights, `adapter_config.json`, tokenizer), `training_args.json`, `provenance.json` (base id, revision,
resolved commit, dataset sha256), `loss_log.jsonl`, `environment.json` and a README with the exact command.
