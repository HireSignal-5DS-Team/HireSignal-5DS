# Soft prompt tuning of the Matcher (Session 3, EXPERIMENTAL)

Status (2026-10-16): **implemented, tested and smoke-run on a tiny random model only. No 4B soft prompt has been
trained and no 4B arm has been evaluated.** Compute window 0 forbids model training and inference in the shared
containers, so the 4B runs are handed off to a Kaggle GPU notebook. This code is opt-in experiment code. It is never
a production default and does not touch the production Matcher, `matcher/factory.py` or the llama.cpp serving path.

| stage | state |
|---|---|
| soft prompt trainer (`train_soft_prompt.py`, PEFT prompt tuning) | implemented; tested on a tiny random Qwen3 |
| four-arm backend + evaluator (`backend.py`, `evaluate.py`) | implemented; tested on a tiny random Qwen3 |
| paired comparison (`compare.py`) | implemented; tested |
| compatibility check (`compat_check.py`) | **run, MEASURED** (metadata + tokenizer, no weights): all checks pass |
| feasibility (`estimate.py --probe`) | **run, MEASURED** on random full-width slices of the 4B model, extrapolated |
| CPU smoke run, whole pipeline (`smoke.py`) | **run, SMOKE** (tiny random model, real data files) |
| Kaggle handoff (`make_bundle.py`, `kaggle_soft_prompt.ipynb`) | ready; **not run** |
| 4B training and the 4-arm comparison on the 202 val requirements | **pending** (Kaggle GPU, or CPU in window 1) |

## 1. Method

This is **trainable soft prompt tuning** (Lester et al., 2021), not prompt engineering. It uses PEFT
`PromptTuningConfig` with `PromptTuningInit.TEXT`.

- The model learns `num_virtual_tokens` vectors, shape `[32, 2560]`, which gives **81,920 trainable parameters**.
  They are prepended to the input embeddings of every example.
- The backbone stays frozen (`requires_grad=False` on all 4.02 B weights). Tests check that only the soft prompt
  receives a gradient, with and without gradient checkpointing.
- The gradient still has to flow back through all 36 layers to reach the input positions. Training therefore costs
  about the same compute as LoRA, even though it updates far fewer parameters.

| setting | value | note |
|---|---|---|
| backbone | `Qwen/Qwen3-4B-Instruct-2507` @ `cdbee75f…` | the revision the Matcher LoRA was trained on |
| virtual tokens | 32, init from the token embeddings of `common.INIT_TEXT` | text init is the stable PEFT default |
| prompt | Matcher prompt p1 (`matcher/prompt.py`), chat template, `add_generation_prompt=True` | virtual tokens sit before `<\|im_start\|>system` |
| loss | assistant tokens only; prompt and virtual tokens are -100 | same `encode()` as `finetune/train_lora.py` |
| optimiser | AdamW lr 3e-2, 6 % warm-up, linear decay, grad-clip 1.0, batch 1 × accum 16 | the soft prompt stays fp32 whatever the backbone dtype |
| epochs | 3 (129 optimizer steps: ceil(681 / 16) = 43 per epoch) | |
| precision | backbone bf16 where supported, else fp16 + `GradScaler` (T4/P100) | |
| selection | lowest val loss on `sft_val.jsonl`, evaluated once per epoch | see the caveat in §6 |
| seed | 13; the example order is fixed by the seed | an interrupted run resumes bit-exactly (tested) |

**Data.** Training reads only `finetune/data/sft_train.jsonl`: 681 examples from the 150 train cases, sha256
`1d944d2f…`.

Val is used in two ways:
- `sft_val.jsonl` gives the val loss used to select the checkpoint;
- `prompt_tuning/data/val_prompts.jsonl` holds the 202 val prompts for evaluation. It has no targets.

The prompts in `val_prompts.jsonl` are rendered with the team BM25 RAG (k=3). They are asserted identical to the
prompts in `sft_val.jsonl`, and also identical to `finetuning/data/val_prompts.jsonl` on
`feature/qwen3-4b-finetune-handoff`, so this is the team's evaluation input.

The locked test split is never read for content. `prepare_data.py` reads only its case_ids and CV texts, for the
leakage audit. The trainer refuses:
- files whose name looks like val or test;
- any case_id that belongs to val or test;
- non-train ids;
- a selection file containing anything other than val ids.

Leakage audit (`data/manifest.json`), train against val and against test:
- 0 shared case_ids;
- 0 exact CV duplicates;
- 0 shared requirement texts;
- max 6-gram Jaccard 0.0.

## 2. Compatibility findings

These are measured by `python -m prompt_tuning.compat_check` from metadata and the tokenizer only. Output:
`benchmark/results/experimental/soft_prompt/compat_check.json`.

- **Tokenizer and chat template.**
  - The architecture is `Qwen3ForCausalLM`, hidden size 2560, tied embeddings.
  - The Instruct-2507 template has no thinking mode: `enable_thinking=False` is a no-op, and no `<think>` block
    appears.
  - eos is `<|im_end|>` and pad is `<|endoftext|>`.
  - The LoRA repo's `tokenizer.json` is **not byte-identical** to the base's. Only the serialised ByteLevel
    pre-tokenizer and decoder defaults differ. The vocab is the same, the special tokens are the same, and the token
    ids are identical on all 883 train and val SFT texts. The LoRA's `chat_template.jinja` is identical to the base's.
    The pipeline always uses the base tokenizer.
- **PEFT.**
  - `requirements-matcher.txt` pins `peft==0.21.2`, the same version that wrote the Matcher LoRA (`peft_version`
    in its adapter_config). `transformers==5.19.0` and `torch==2.14.1` were installed and used here.
  - `PromptTuningConfig` works with Qwen3 in this version: training, save, load and generate are all tested.
  - One PEFT limit matters: PEFT refuses to load a prompt-learning adapter as trainable. A resume therefore rebuilds
    the soft prompt and copies the saved tensor into it (`model.resume_soft_prompt`, tested).
- **The Matcher LoRA** (`HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora` @ `0b6925b1…`).
  - Its config: PEFT LoRA, r=16, alpha=32, q/k/v/o/gate/up/down; base `Qwen/Qwen3-4B-Instruct-2507`, trained on
    revision `cdbee75f…`.
  - **A soft prompt can be trained on top of it.** PEFT allows only one adapter type per model, so the LoRA is merged
    first (`merge_and_unload`). The merged model is a plain `Qwen3ForCausalLM`, which is frozen and then wrapped with
    prompt tuning. A test confirms that the merge changes the weights and leaves no LoRA modules.
  - A soft prompt records the backbone it was trained on (`hs_soft_prompt.json`) and refuses to attach to a different
    one: base vs merged LoRA, other LoRA, other revision. This is tested.
  - Caveat: the LoRA was trained as a QLoRA, against **4-bit NF4** base weights with fp16 compute. Here it is merged
    into fp16/bf16 weights, so its behaviour can shift slightly. The same merged weights are used in both LoRA arms,
    so `lora` and `lora_soft_prompt` differ only by the soft prompt.
  - The LoRA was trained on different data: 777 examples, 505 synthetic bench plus 272 ContractNLI, sha
    `f8eff94a…`. The soft prompts are trained on the 681 `sft_train` examples. This is a property of the existing
    adapter and is reported, not hidden.
- **Inference backend.**
  - llama.cpp/GGUF (the production serving path, `scripts/serve_qwen4b_lora.sh`) **cannot load PEFT prompt
    embeddings**. Its OpenAI-compatible server only takes text or token ids. The C API's `llama_batch.embd` can take
    raw embeddings, but nothing in this repo or in llama-cpp-python's server exposes it. It has not been implemented
    or tested here.
  - `matcher/backends.py:TransformersBackend` cannot be used either. It refuses models with 1 B parameters or more
    (`MAX_PARAMS`) and knows only LoRA adapters.
  - Inference therefore runs through `prompt_tuning/backend.py:SoftPromptBackend`: transformers, PEFT
    `generate()`, greedy decoding, max 192 new tokens. Its interface (`generate(task)`, `info()`) plugs into
    `matcher.agent.Matcher`.
  - The soft prompt is also exported as a plain tensor (`soft_prompt.safetensors`, key `soft_prompt`). A test shows
    that `generate(inputs_embeds=concat(soft_prompt, embed(ids)))` without PEFT produces exactly the same text, so
    any runtime that accepts input embeddings can serve it.
- **Is the comparison equal?** Not if the soft prompt arms run in transformers fp16 while the team's base and LoRA
  numbers come from llama.cpp Q4_K_M. The quantisation and the runtime differ.
  - **Design:** all four arms are re-run through the same `SoftPromptBackend`, with the same dtype, device, decoding,
    prompts, validator and metrics.
  - `compare.py` refuses to put arms with different dtype, device or decoding, or different labels, in one table.
  - The team's llama.cpp numbers stay a separate reference.
  - Deployment consequence: a soft prompt Matcher would need a transformers runtime (about 8 GB of 16-bit weights
    instead of 2.5 GB for Q4) or new llama.cpp embedding-input code.

## 3. Feasibility

These are measured with `python -m prompt_tuning.estimate --probe` (`feasibility.json`) on this container: 4 vCPU,
15 GiB RAM, no GPU.

Method:
- No 4B weights were loaded.
- Real fwd+bwd, prefill and decode steps were timed on random Qwen3 slices with the 4B model's exact widths
  (hidden 2560, MLP 9728, 32/8 heads, 151,936 vocab, tied embeddings), with 1 and 3 layers.
- The per-layer slope was extrapolated to 36 layers.
- Sequence length: 454 tokens + 32 virtual tokens, the mean of `sft_train`.
- The bf16 GEMM peak was measured at 1216 GFLOP/s (fp32: 438).

| quantity | CPU bf16 (measured + extrapolated) | CPU fp32 | Kaggle T4 fp16 (estimate, not measured) |
|---|---|---|---|
| backbone weights in memory | 8.0 GB, fits 15 GiB | 16.1 GB, **does not fit** | 8.0 GB of 15 GB VRAM |
| train step (1 example, grad ckpt) | 13.5 s | 24.6 s | ≈ 1.5–2.5 s |
| one soft prompt, 3 epochs + val loss | **≈ 8.5 h** (7.7 h train + 0.8 h val loss) | — | **≈ 1–1.5 h** |
| eval, per requirement | ≈ 14 s (prefill 4.6 s + 60 × 0.16 s decode) | ≈ 24 s | ≈ 3–6 s |
| eval, one arm × 202 | ≈ 0.8 h | — | ≈ 10–20 min |
| **whole study: 2 soft prompts + 4 arms** | **≈ 20 h of exclusive container time** | infeasible | **≈ 3–4 h, one Kaggle session** |

- **The Kaggle T4 numbers are estimates.** They are anchored on a measured run: the Matcher LoRA's QLoRA training on
  Kaggle took 3443 s for 1554 example passes, about 2.2 s per example with 4-bit dequantisation and grad ckpt
  (`train_meta.json` of the adapter). The FLOP count (26 PFLOP for 3 epochs) gives 0.4–0.9 h at 8–20 effective
  TFLOP/s.
- The CPU numbers are extrapolations from real timed slices.
  - Extra memory for a 4B bf16 run is not measured. Estimate: about 0.4 GB fp32 logits, about 0.13 GB checkpointed
    activations, plus runtime overhead, so roughly 10–11 GB peak.
  - bf16 CPU training differs numerically from GPU fp16.
- **Decision.**
  - CPU training of the 4B model is *possible in bf16*, but it costs about 20 h of a shared container, after every
    other window-1 job.
  - The trainer refuses CPU backbones above 200 M parameters unless `--allow-large-cpu` is given.
  - The plan is the Kaggle handoff below, as `ORCHESTRATION.md §5` prescribes.
  - The CPU smoke test proves the pipeline end to end.

## 4. Commands

Setup, from the repo root, with pinned `requirements-matcher.txt`:

```bash
# 0. inputs (already committed; re-run only if sft_*.jsonl or the RAG changes)
HIRESIGNAL_RAG_DIR=<checkout of rag/ from claude/gracious-fermi-ncuem4> python -m prompt_tuning.prepare_data
python -m prompt_tuning.compat_check                       # metadata + tokenizer only
nice -n 19 python -m prompt_tuning.estimate --tokenizer Qwen/Qwen3-4B-Instruct-2507 \
    --revision cdbee75f17c01a7cc42f958dc650907174af0554 --probe
nice -n 19 python -m prompt_tuning.smoke                   # tiny random model, ~20 s, writes .../soft_prompt/smoke/
python -m pytest prompt_tuning/tests                       # 15 tests
```

**Kaggle (GPU T4 x2 or P100, Internet ON).**

1. Run `python -m prompt_tuning.make_bundle`. It writes `prompt_tuning/dist/hiresignal_soft_prompt_bundle.zip`:
   283 KB, 48 files, no test split.
2. Upload the zip as a **private** dataset named `hiresignal-soft-prompt`.
3. Import `prompt_tuning/kaggle_soft_prompt.ipynb` and add the dataset.
4. Run all cells:
   - integrity and sha check;
   - base and LoRA eval;
   - training of the two soft prompts;
   - eval of the two soft prompt arms;
   - comparison;
   - zips.

   Every cell is resumable.
5. Download `soft_prompt_results.zip` and `soft_prompt_runs.zip`. Commit them under
   `benchmark/results/experimental/soft_prompt/`. Each soft prompt is about 0.7 MB (PEFT file + plain tensor export); checkpoints are excluded.

The notebook runs these, with `DTYPE` = bfloat16 if the GPU supports it, else float16, for **all** arms:

```bash
python -m prompt_tuning.evaluate --arm base --device cuda --dtype $DTYPE --run-id base-$DTYPE-val
python -m prompt_tuning.evaluate --arm lora --lora $LORA --lora-revision $LREV --device cuda --dtype $DTYPE --run-id lora-$DTYPE-val
python -m prompt_tuning.train_soft_prompt --run-id sp-base-v1 --device cuda --dtype $DTYPE --grad-ckpt
python -m prompt_tuning.train_soft_prompt --run-id sp-lora-v1 --lora $LORA --lora-revision $LREV --device cuda --dtype $DTYPE --grad-ckpt
python -m prompt_tuning.evaluate --arm soft_prompt --soft-prompt runs/sp-base-v1/soft_prompt --device cuda --dtype $DTYPE --run-id sp-base-v1-$DTYPE-val
python -m prompt_tuning.evaluate --arm lora_soft_prompt --lora $LORA --lora-revision $LREV \
    --soft-prompt runs/sp-lora-v1/soft_prompt --device cuda --dtype $DTYPE --run-id sp-lora-v1-$DTYPE-val
python -m prompt_tuning.compare --runs base=base-$DTYPE-val lora=lora-$DTYPE-val \
    soft_prompt=sp-base-v1-$DTYPE-val lora_soft_prompt=sp-lora-v1-$DTYPE-val
```

`LORA=HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora` and `LREV=0b6925b1e3c89b6b266b10bcd30af4c6a0c2dc3a`.

**CPU in window 1.** This is only if the orchestrator assigns about 20 h, under `flock /home/user/hs_queue.lock`.
Use the same commands with `--device cpu --dtype bfloat16 --allow-large-cpu`. All four arms must then also be
evaluated in CPU bf16.

## 5. Results

On the 202 val requirements. Every cell is labelled.

| arm | macro-F1 | false-MET | JSON valid | UNCERTAIN rate | latency p50 / p95 | peak RSS / VRAM | status |
|---|---|---|---|---|---|---|---|
| `base` (Qwen3-4B, transformers, same dtype) | pending | pending | pending | pending | pending | pending | **PENDING** (Kaggle) |
| `lora` (Matcher LoRA merged) | pending | pending | pending | pending | pending | pending | **PENDING** (Kaggle) |
| `soft_prompt` | pending | pending | pending | pending | pending | pending | **PENDING** (training + eval) |
| `lora_soft_prompt` (feasible, see §2) | pending | pending | pending | pending | pending | pending | **PENDING** (training + eval) |

- **Smoke run (SMOKE, plumbing only).** `smoke/COMPARISON_SMOKE.md` evaluates all four arms of a tiny random Qwen3
  on the first 20 val prompts, with soft prompts trained for 6 steps.
  - Every arm gets macro-F1 0.061, JSON-valid 0.000 and UNCERTAIN 1.000. A random model writes no JSON, so the
    validator routes everything to UNCERTAIN.
  - All four arms ran in one process, so the peak RSS (962 MB) is shared, not per arm.
  - These numbers say nothing about the Matcher.
- **Reference, different backend, not comparable to the table above:** untuned Qwen3-4B Q4_K_M through llama.cpp,
  `benchmark/results/qwen3-4b-q4-rag-val`, MEASURED by the team: macro-F1 0.630, false-MET 0.009, JSON valid 0.916,
  p50 16.4 s and p95 34.3 s on CPU.
  - Also on llama.cpp Q4_K_M, 202 val requirements, without RAG, as reported by the orchestrator on 2026-10-16
    (artefacts on `claude/kind-albattani-k7qlt9`, not re-checked here): base 0.634 and Matcher LoRA 0.908 macro-F1.
    These are GGUF numbers. They are never mixed into the transformers-backend table above.

**Pre-registered decision rule.** The soft prompt (or LoRA + soft prompt) is kept as an experimental candidate only
if, against `base` and `lora` respectively under the same backend:
- macro-F1 is higher, with the paired bootstrap 95 % CI excluding 0;
- the false-MET rate is not higher;
- JSON validity is not lower.

Otherwise the result is reported as negative. The test split is unlocked only by the orchestrator, once, for a
configuration already selected on val.

**Reproducibility.** Each artefact records what produced it:
- Training run (`prompt_tuning/runs/<id>/`): `training_args.json`, `provenance.json` (backbone ids and revisions,
  train/val/manifest sha256, selected step, `train_config_hash`, `soft_prompt_sha256`), `environment.json`,
  `loss_log.jsonl`, `README.md` with the exact command.
- Eval run: `config.json` with `config_hash` (arm, backend info, prompts/gold sha256, dtype, device, decoding),
  versions, git commit and command. A resume under a changed config is refused.
- Inside the training run, any change to a result-affecting argument under the same run id is refused, including
  the step budget and the eval cadence.

## 6. Caveats

- **Selection on val.** As instructed, checkpoint selection uses the val loss, and the four-arm comparison uses the
  same val requirements. This gives the soft prompt arms a mild selection advantage over `base`/`lora`: one choice
  among 3 checkpoints, by loss, not by F1. The trainer has `--select-on last` for an unbiased variant.
- The `lora` arm here is the Matcher LoRA merged into 16-bit weights. That is neither its training condition (NF4)
  nor its production condition (GGUF f16 LoRA on Q4_K_M).
- Qwen3 in fp16 (T4/P100) can overflow. The trainer stops on a non-finite loss; prefer a bf16 GPU if available.
- The SFT gold explanations are one fixed sentence per decision. A soft prompt, like the LoRA, learns decision,
  basis and quote format, not explanation quality.

## 7. Files

| file | role |
|---|---|
| `common.py` | pinned ids, paths, hashing, leakage checks |
| `prepare_data.py` | val prompts with RAG refs + manifest + leakage audit |
| `model.py` | frozen backbones (base / merged LoRA), new / save / load / resume soft prompt, backbone identity |
| `train_soft_prompt.py` | resumable trainer, val-loss selection, fp16 GradScaler, CPU guard |
| `backend.py` | `SoftPromptBackend`: one transformers backend for the four arms |
| `evaluate.py` | one arm on val → `predictions.jsonl` / `metrics.json` (benchmark format + memory, latency, hash) |
| `compare.py` | four-arm table, exact McNemar, bootstrap CI; refuses unequal setups or mixed labels |
| `compat_check.py`, `estimate.py` | §2 and §3 |
| `tiny.py`, `smoke.py` | tiny random Qwen3 + LoRA; end-to-end CPU smoke run |
| `make_bundle.py`, `kaggle_soft_prompt.ipynb` | GPU handoff |
| `tests/test_soft_prompt.py` | 15 tests (see below) |

The tests run on a tiny random Qwen3. They cover:
- leakage refusals in the code and in the committed data;
- that only the `[n, hidden]` soft prompt gets a gradient, with and without grad ckpt;
- the text-init values;
- a bit-exact resume after a simulated crash;
- refusal of changed arguments;
- val-loss selection;
- the save/load round trip;
- PEFT generate == manual `inputs_embeds` generate;
- that the soft prompt changes the logits;
- LoRA merge and backbone-identity refusal;
- the fp16 GradScaler path;
- the CPU guard;
- four-arm evaluation, resume and config-change refusal;
- refusal of test prompts;
- refusal of unequal comparisons;
- McNemar;
- the parameter count (4.022 B).
