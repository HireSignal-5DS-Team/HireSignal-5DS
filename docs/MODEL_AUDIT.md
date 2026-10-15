# HireSignal Matcher: Model Audit (sub-1B generative SLM)

Status: **verified against the Hugging Face Hub and loaded locally** (2026-10-14/15).
Every model below was checked with `huggingface_hub` (`model_info`, `config.json`, `generation_config.json`,
`LICENSE`/`README.md`) at the exact commit sha given. The loadable arms were downloaded, loaded on CPU and
smoke-tested with the Matcher prompt. Machine-readable list: `models/candidates.json`.
Raw smoke outputs: `models/smoke_results.json`. Script: `models/verify_models.py`.

## Constraint recap

- Exactly ONE generative small language model, **strictly < 1B total parameters (embeddings included)**.
  Enforced in code: `matcher.backends.MAX_PARAMS` checks `sum(p.numel())` after load.
- Optional: one compatible LoRA adapter on that model (`check_adapter_compat` refuses another base).
- Task: per job requirement, read anonymized CV + requirement + ESCO definitions. Emit strict JSON
  `{decision: MET|MISSING|UNCERTAIN, basis, evidence: [verbatim CV quotes], explanation}`.
- Hardware: CPU 4 cores / 15 GB RAM (primary). Windows laptop with GPU (local dev).
- The old Qwen3-4B / Ollama 4B architecture is **CANCELLED**. It is over budget and must not be used.

## How facts were checked

- **[F]** = fetched from the Hub at the sha given (config, card, LICENSE, file list), or measured locally.
- **[L]** = measured locally in this container: torch 2.14.1 (CPU), transformers 5.19.0, peft 0.21.2,
  huggingface_hub 2.2.0, 4 shared CPU cores, float32, greedy decoding, `max_new_tokens=160`.
- No HF token was used. Gated repos were recorded and skipped.
- The earlier [S]/UNVERIFIED claims of this file were replaced. Where the old claim was wrong, it is called out.

## Summary table (Hub facts)

| Model id | Revision (sha) | License tag [F] | Params, safetensors header [F] | Context (`max_position_embeddings`) [F] | Verdict |
|---|---|---|---|---|---|
| Qwen/Qwen2.5-0.5B-Instruct | `7ae557604adf67be50417f59c2c2f167def9a775` | apache-2.0 | 494,032,768 | 32,768 | **Candidate** (adapter base) |
| Qwen/Qwen3-0.6B | `c1899de289a04d12100db370d81485cdf75e47ca` | apache-2.0 | 751,632,384 in file; 596,049,920 loaded (tied) | 40,960 | **Candidate** |
| Qwen/Qwen3.5-0.8B (new) | `2fc06364715b967f1860aea9cf38778875588b17` | apache-2.0 | 873,438,784 (incl. vision); 752,393,024 loaded as CausalLM | 262,144 | **Candidate** (strongest smoke) |
| HuggingFaceTB/SmolLM2-360M-Instruct | `a10cc1512eabd3dde888204e902eca88bddb4951` | apache-2.0 | 361,821,120 | 8,192 | Speed floor |
| ibm-granite/granite-4.0-350m (new) | `bd8a1497065c0d6ba1ef19af6b0d2b14bacf71c2` | apache-2.0 | 352,379,904 | 32,768 | Optional extra |
| LiquidAI/LFM2.5-350M (new) | `9e6c6ccf47cd318696e137d381a7ded8fe4df09f` | other (`lfm1.0`) | 354,483,968 | 128,000 | Optional extra (license) |
| LiquidAI/LFM2-350M | `f37d3f5c8c5484bc01dad379a595cf4c68c4e70e` | other (LFM Open License v1.0) | 354,483,968 | 128,000 | Superseded by LFM2.5-350M |
| LiquidAI/LFM2-700M | `86f49fc9a3800c3a325b7320bde179c318062583` | other (LFM Open License v1.0) | 742,489,344 | 128,000 | Not loaded (metadata only) |
| google/gemma-3-270m-it | `ac82b4e820549b854eebf28ce6dedaf9fdfa17b3` | gemma | 268,098,176 | not read (gated) | **Gated (`manual`)**: skipped |
| Kus-hal/resume-screener-lora | `e4c042f538b4a899b9aa2f2d38bbc39d27fb7aa6` | mit | 2,162,688 LoRA params | n/a | Loads; **wrong output format** |
| gw0/jobfit-model | `392cc1d48f75044a354abb08de4c73fbb62ca421` | apache-2.0 (weights card) | ONNX only | 8,192 | Reference-only |

Corrections to the earlier [S] draft:
- Qwen3-0.6B `max_position_embeddings` is **40,960**, not 32,768 (card speaks of 32,768 context).
- LFM2-350M / LFM2-700M configs say **128,000**, not 32,768.
- SmolLM2-360M-Instruct context is confirmed **8,192**.
- Kus-hal adapter license is **MIT** and `adapter_model.safetensors` **exists**.
- gw0/jobfit-model weights card says **apache-2.0** (the GitHub code is AGPL-3.0-or-later).

## Verified locally [L]

Loaded with `matcher.backends.TransformersBackend` (float32, CPU), one arm per subprocess, sequentially.
Smoke = 2 hand-made examples via `matcher.agent.Matcher` + `NoKnowledge`:
r1 "Experience building REST APIs in Python" (gold MET/supported, quote exists in CV),
r2 "Kubernetes administration" (gold MISSING/not_documented).
"JSON ok" = `parse_model_output` returned a valid `ModelAnswer`. Latency = seconds per requirement on a
CPU shared with other agents, so it is noisy. **Two examples prove loading and format only, not quality.**

| Arm | Exact params `sum(p.numel())` | Weights on disk (MB) | Load s | RSS after load (MB) | JSON ok r1 / r2 | Model decision r1 / r2 | Latency s r1 / r2 |
|---|---|---|---|---|---|---|---|
| qwen2.5-0.5b | 494,032,768 | 942 | 2.13 | 2,708 | yes / **no** | MISSING (wrong) / - | 4.5 / 4.2 |
| qwen2.5-0.5b + Kus-hal LoRA | 494,032,768 + 2,162,688 = 496,195,456 | 942 + 8 | 2.37 | 2,716 | no / no | - / - | 12.1 / 7.8 |
| qwen3-0.6b (`enable_thinking=False`) | 596,049,920 | 1,434 | 2.26 | 3,105 | no / yes | - / UNCERTAIN | 7.7 / 6.5 |
| qwen3.5-0.8b (`enable_thinking=False`) | 752,393,024 | 1,666 | 2.83 | 5,201 | **yes / yes** | **MET / MISSING** | 12.3 / 11.4 |
| smollm2-360m | 361,821,120 | 690 | 1.94 | 2,135 | no / no | - / - | 4.9 / 19.8 |
| granite-4.0-350m | 352,379,904 | 672 | 2.18 | 2,168 | no / no | - / - | 3.3 / 3.1 |
| lfm2-350m | 354,483,968 | 676 | 1.33 | 2,139 | no / no | - / - | 4.4 / 4.1 |
| lfm2.5-350m | 354,483,968 | 676 | 1.61 | 2,146 | yes / yes | MET / MET (wrong) | 3.4 / 3.9 |

Failure modes seen in the raw outputs (`models/smoke_results.json`):
- qwen2.5-0.5b r2: invented labels `"decision": "NOT DOCUMENTED"`, free-text basis. r1 said MISSING although
  the CV says "Built REST APIs in Python with FastAPI".
- qwen3-0.6b r1 and smollm2-360m: copied the schema placeholder (`"MET|MISSING|UNCERTAIN"`) instead of choosing.
- granite-4.0-350m: `evidence` as a string, not a list (schema fail); r2 claims MET for Kubernetes.
- lfm2-350m: not JSON (`MET|MISSING|UNCERTAIN|{...}`).
- lfm2.5-350m and qwen3.5-0.8b: copied the placeholder quote `"exact quote copied from the CV"`. The validator
  rejects it (not a CV substring), so MET was downgraded to UNCERTAIN. qwen3.5-0.8b r2 used basis `contradicted`
  with no evidence; validated result is still MISSING/not_documented.
- Common to all: none produced a real verbatim CV quote. The prompt example quote is being copied.
  This is a prompt issue (`matcher/prompt.py`, owned elsewhere) and/or a LoRA-training target. Not a model blocker.

Memory: float32 RSS is ~2.1-3.1 GB for the 0.35-0.6B arms and ~5.2 GB for Qwen3.5-0.8B (248k vocab).
All fit the 15 GB box. bf16 would roughly halve this; not tested here.

## Per-model notes

### 1. Qwen/Qwen2.5-0.5B-Instruct

- Revision `7ae557604adf67be50417f59c2c2f167def9a775`. License apache-2.0, LICENSE file present [F].
- Config [F]: `Qwen2ForCausalLM`, 24 layers, hidden 896, intermediate 4864, 14 Q / 2 KV heads,
  vocab 151,936, `tie_word_embeddings: true`, `max_position_embeddings` 32,768, stored bf16,
  config written by transformers 4.43.1.
- Params [L]: **494,032,768** (matches the earlier computed value and the Hub safetensors header).
- `generation_config.json` [F]: `do_sample: true, temperature 0.7, top_p 0.8, top_k 20, repetition_penalty 1.1`.
  The Matcher overrides with greedy (`do_sample=False`).
- No thinking mode. ChatML template.

### 2. Qwen/Qwen2.5-0.5B-Instruct + Kus-hal/resume-screener-lora

- Adapter revision `e4c042f538b4a899b9aa2f2d38bbc39d27fb7aa6`. License tag **mit** [F].
- `adapter_config.json` [F]: `base_model_name_or_path: "Qwen/Qwen2.5-0.5B-Instruct"`, `peft_type: "LORA"`,
  `task_type: "CAUSAL_LM"`, `r: 16`, `lora_alpha: 32`, `lora_dropout: 0.05`,
  `target_modules: [k_proj, o_proj, q_proj, v_proj]`, `use_dora: false`, `use_rslora: false`, `bias: none`.
- Files [F]: `adapter_model.safetensors` (8,676,008 bytes, 192 tensors, **2,162,688 params**), plus
  tokenizer files (same added special tokens as the base; no new tokens), `training_args.bin`.
  The Hub `pipeline_tag` is `text-classification`, but the adapter is a causal-LM LoRA.
- Card [F]: 800 train / 96 eval examples, 3 epochs on a Colab T4, val loss 0.2784 to 0.1714. Data source not given
  beyond "dataset generator" in https://github.com/ayush-s-tomar/resume-screener-lora.
- **`check_adapter_compat` passes** [L]: `TransformersBackend("Qwen/Qwen2.5-0.5B-Instruct",
  adapter_id="Kus-hal/resume-screener-lora")` loaded with no error. Total 496,195,456 params, < 1B.
  Note: `TransformersBackend.n_params` counts the base before the adapter is attached (reports 494,032,768).
- Output format [L]:
  - On its native prompt (card example style, no system prompt) it emits its own schema:
    `{"role": "Backend Engineer", "ats_score": 56, "verdict": "moderate_match", "matched_skills": [...],
    "missing_skills": ["REST API", "Java", "Kubernetes"], "years_experience": 2}`.
    `ats_score` 56 equals the card's example, and "REST API" is listed missing although the CV has it:
    looks template-memorized.
  - On the Matcher prompt it breaks our schema: invents `"decision": "CONTRADIZED"`, free-text basis, quotes the
    requirement as CV evidence, and emits several objects. **0/2 JSON-valid.**
- Verdict: **experiment arm only, likely to lose**. It hurts our contract compared to the bare base.
  A LoRA trained on our own `train.jsonl` with `prompt.target()` is the better adapter path.

### 3. Qwen/Qwen3-0.6B

- Revision `c1899de289a04d12100db370d81485cdf75e47ca`. License apache-2.0 [F].
- Config [F]: `Qwen3ForCausalLM`, 28 layers, hidden 1024, intermediate 3072, 16 Q / 8 KV heads, head_dim 128,
  vocab 151,936, `tie_word_embeddings: true`, `max_position_embeddings` **40,960**, config transformers 4.51.0.
- Params [L]: **596,049,920**. The safetensors file also stores a separate `lm_head.weight` (header total
  751,632,384), but the config ties it to the embeddings, so the loaded model has 596,049,920.
- `generation_config.json` [F]: thinking defaults `temperature 0.6, top_p 0.95, top_k 20, do_sample true`.
- Card [F]: thinking on by default; `enable_thinking=False` disables it. Non-thinking recommendation:
  `Temperature=0.7, TopP=0.8, TopK=20, MinP=0`. `transformers<4.51.0` raises `KeyError: 'qwen3'`.
- Smoke [L]: no `<think>` block with `enable_thinking=False`. Copied the schema placeholder on r1.

### 4. Qwen/Qwen3.5-0.8B (newly found)

- Revision `2fc06364715b967f1860aea9cf38778875588b17`, created 2026-02-28. License apache-2.0 [F].
- It is a vision-language checkpoint (`Qwen3_5ForConditionalGeneration`, `model_type: qwen3_5`, 153 vision tensors).
  Full checkpoint 873,438,784 params [F], still < 1B.
- `AutoModelForCausalLM` loads the text model only [L]: **752,393,024** params. Text config [F]: 24 layers
  (hybrid: 3 linear-attention + 1 full-attention per block of 4), hidden 1024, intermediate 3584, 8 Q / 2 KV heads,
  vocab 248,320, tied embeddings, `max_position_embeddings` 262,144. No `generation_config.json`.
- Card [F]: "Qwen3.5-0.8B operates in non-thinking mode by default". Non-thinking text sampling recommendation:
  `temperature=1.0, top_p=1.00, top_k=20, min_p=0.0, presence_penalty=2.0`. We keep greedy for determinism.
- Smoke [L]: only arm with 2/2 JSON-valid and both decisions right before validation. Slowest (~12 s/req)
  and largest RSS (5.2 GB fp32).

### 5. Other sub-1B instruct models

- **HuggingFaceTB/SmolLM2-360M-Instruct** [F]: `LlamaForCausalLM`, 32 layers, hidden 960, vocab 49,152,
  ctx 8,192, apache-2.0. Params [L] 361,821,120. Smoke: 0/2 JSON (echoes the schema). An 8k context also
  limits long CVs.
- **ibm-granite/granite-4.0-350m** [F] (new, 2025-10-07): `GraniteMoeHybridForCausalLM` (all-attention variant),
  28 layers, hidden 1024, vocab 100,352, ctx 32,768, apache-2.0. Params [L] 352,379,904. Smoke: 0/2 JSON
  (evidence as string) and hallucinated MET. Sibling `granite-4.0-h-350m` (340,332,224, hybrid Mamba) not loaded.
- **LiquidAI/LFM2.5-350M** [F] (new, 2026-03-31): `Lfm2ForCausalLM`, 16 layers (10 conv + 6 attention),
  hidden 1024, vocab 65,536, ctx 128,000, license `other` / `lfm1.0`. Params [L] 354,483,968. Smoke: 2/2 JSON but
  said MET for Kubernetes. Fastest valid-JSON arm (~3.5 s/req).
- **LiquidAI/LFM2-350M / LFM2-700M** [F]: LFM Open License v1.0 (LICENSE file read). Section 5: commercial use is
  licensed only for entities under **USD 10M annual revenue**. LFM2-350M loads with transformers 5.19.0
  (native `lfm2`), params [L] 354,483,968, smoke 0/2 JSON. LFM2-700M not loaded (742,489,344 per Hub header).
- **google/gemma-3-270m-it** [F]: `gated: manual`, license `gemma`, Hub header 268,098,176 params.
  Gated, so config and weights were **not** downloaded (no tokens used). Skipped.
- Also seen on the Hub, not loaded: `tiiuae/Falcon-H1-0.5B-Instruct` (521,411,104, `falcon-llm-license`),
  `openbmb/MiniCPM4-0.5B` (433,873,920, apache-2.0, needs `trust_remote_code`, so avoided),
  `LiquidAI/LFM2.5-230M` (229,693,184, lfm1.0). No Qwen3.5 / SmolLM3 text model below 1B other than
  Qwen3.5-0.8B was found (SmolLM3 is 3B only).

### 6. Recruitment / resume LoRA adapters on < 1B bases (Hub search: resume, cv, job, recruit, hiring, candidate)

Base and license read from each `adapter_config.json` / card [F]. None was loaded except Kus-hal.

| Adapter | Revision | Base (`base_model_name_or_path`) | r / alpha | License | Purpose (card) |
|---|---|---|---|---|---|
| Kus-hal/resume-screener-lora | `e4c042f5…` | Qwen/Qwen2.5-0.5B-Instruct | 16 / 32 | mit | whole-resume verdict JSON |
| sandeeppanem/qwen3-0.6b-resume-json | `f3e8ffcc…` | Qwen/Qwen3-0.6B | 8 / 16 | apache-2.0 | resume parsing to JSON |
| jonathanjordan21/Qwen2-0.5-Instruct-lora-resume-parser | `6598c42e…` | Qwen/Qwen2-0.5B-Instruct | 64 / 64 | apache-2.0 | resume parser, data unknown |
| lildatascientist/qwen2.5-resume-lora | `63f35d7d…` | Qwen/Qwen2.5-0.5B-Instruct | 16 / 32 | none | empty template card |
| g-tertho/cv-qwen3-lora-v2 | `cb52d1b5…` | Qwen/Qwen3-0.6B | 16 / 32 | none | empty template card |
| thananchayan/gemma3-resume-lora | `3b7484ea…` | google/gemma-3-270m-it (gated base) | 16 / 32 | none | empty template card |

None of them targets per-requirement MET/MISSING/UNCERTAIN with verbatim evidence. Adapters with no license
must not be shipped. Many `cvoffer/*` and `joboffer/*` hits are hash-named generic adapters, not recruitment models.

### 7. gw0/jobfit-model (reference baseline only)

- Revision `392cc1d48f75044a354abb08de4c73fbb62ca421`, card license apache-2.0, `library_name: transformers.js` [F].
- Files [F]: `onnx/model_quantized.onnx` (136,558,068 bytes), `calibration.json`, tokenizer; no safetensors.
  Base `HuggingFaceTB/SmolLM2-135M-Instruct`.
- Scores 17 fixed JobFit questions from `lm_head` logits; no free text, no evidence quotes.
  Card: mean MAE 0.1568 (quantized, test). Code on GitHub is AGPL-3.0-or-later.
- Verdict: **reference-only**. Wrong output contract.

### 8. Excluded (>= 1B total params)

- TinyLlama-1.1B: 1.1B. Over the limit.
- Llama-3.2-1B: ~1.2B with embeddings. Over the limit.
- Gemma-3-1B: 999,885,952 per Hub header (gated). Below 1B by a hair, but gated and named "1B";
  excluded to avoid a borderline arm.
- Qwen3-1.7B: 1.7B. Over the limit.
- LFM2-1.2B / LFM2.5-1.2B: 1.2B. Over the limit.
- Qwen3.5-2B, SmolLM3-3B: over the limit.
- Qwen3-4B / Ollama 4B: 4B. Over the limit, and that architecture is **CANCELLED**.

## Recommended benchmark order (CPU-only budget, `val.jsonl` only)

1. **Qwen/Qwen3.5-0.8B** (`enable_thinking=False`). Best smoke result, Apache-2.0, 752M params loaded.
   Cost: ~2.5x slower per requirement than the 0.35B arms and 5.2 GB RSS in fp32.
2. **Qwen/Qwen2.5-0.5B-Instruct** (no adapter). Base for our own LoRA; Apache-2.0.
3. **Qwen/Qwen3-0.6B** (`enable_thinking=False`).
4. **LiquidAI/LFM2.5-350M**. Fast, valid JSON, but LFM license (revenue threshold) must be cleared before use.
5. **Qwen2.5-0.5B-Instruct + Kus-hal LoRA**. Kept as a documented negative control; it breaks our schema.
6. SmolLM2-360M, granite-4.0-350m, LFM2-350M: only if the above all fail (0/2 JSON in smoke).

Score each arm on: JSON validity rate, decision accuracy vs gold, evidence quotes that are verbatim substrings
of the CV, seconds per requirement on the 4-core CPU, peak RAM. Pick ONE model for production.
First fix: no arm produced a real CV quote; the prompt's placeholder quote is copied verbatim.
