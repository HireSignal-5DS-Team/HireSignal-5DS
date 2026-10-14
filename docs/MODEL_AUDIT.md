# HireSignal Matcher: Model Audit (sub-1B generative SLM)

Status: research only. **No model was downloaded, loaded or benchmarked for this audit.**
All numbers below come from web sources. Each fact lists its source and how it was obtained.

## Constraint recap

- Exactly ONE generative small language model, **strictly < 1B total parameters (embeddings included)**.
- Optional: one compatible LoRA adapter on that model.
- Task: per job requirement, read anonymized CV + requirement + ESCO definitions. Emit strict JSON
  `{decision: MET|MISSING|UNCERTAIN, basis, evidence: [verbatim CV quotes], explanation}`.
- Hardware: CPU 4 cores / 15 GB RAM (primary). Windows laptop with GPU (local dev).
- The old Qwen3-4B / Ollama 4B architecture is **CANCELLED**. It is over budget and must not be used.

## How sources were checked (read this first)

- `huggingface.co` could not be fetched. WebFetch failed with `getaddrinfo ENOTFOUND huggingface.co`.
  The container curl gets proxy `403`. Mirrors also failed: `hf-mirror.com`, `modelscope.cn`,
  `ollama.com`, `friendli.ai`, `arxiv.org`, `qwen.readthedocs.io`, `qwenlm.github.io`.
- Only `github.com` / `raw.githubusercontent.com` could be fetched directly.
- Labels used below:
  - **[F]** = fetched directly, URL given.
  - **[S]** = WebSearch result summary that cites the URL given. The page itself was NOT fetched.
    Treat as "likely correct, confirm before release".
  - **[C]** = computed by me from [S] config values. Arithmetic only.
  - **UNVERIFIED — could not fetch** = no source confirmed it.
- Action item: on the Windows laptop (which can reach the Hub), run
  `sum(p.numel() for p in model.parameters())` for each candidate and open each `config.json`.
  That is the only way to turn [S]/[C] into [F].

## Summary table

| Model id | Total params | Verified? | License | Context | Chat template notes | Verdict |
|---|---|---|---|---|---|---|
| Qwen/Qwen2.5-0.5B-Instruct | 0.49B (494,032,768 computed) | [S]+[C] | Apache-2.0 [S] | 32,768 ctx, 8,192 gen [S] | ChatML (`<\|im_start\|>`); no thinking mode | **Candidate #1** (adapter base) |
| Qwen/Qwen3-0.6B | 0.6B (596,049,920 computed) | [S]+[C] | Apache-2.0 [F] (family statement) | 32,768 [S] | ChatML + `enable_thinking`; set `False` | **Candidate #2** |
| HuggingFaceTB/SmolLM2-360M-Instruct | ~362M | [S] | Apache-2.0 [S] | UNVERIFIED (8k suspected) | ChatML-style template | **Candidate #3** |
| LiquidAI/LFM2-350M | 354,483,968 | [S] | LFM Open License v1.0 [S] | 32,768 [S] | Own template; hybrid conv/attn arch | Optional extra |
| LiquidAI/LFM2-700M | 742,489,344 | [S] | LFM Open License v1.0 [S] | 32,768 [S] | Same as LFM2-350M | Optional extra |
| google/gemma-3-270m-it | ~268-270M (~170M are embeddings) | [S] | Gemma Terms of Use [S] | 32,768 [S] | Gemma template, no system role | Optional extra (weak) |
| Kus-hal/resume-screener-lora | LoRA on Qwen2.5-0.5B-Instruct | [S] | UNVERIFIED — could not fetch | n/a | Uses base template | **Adapter candidate** (needs file check) |
| gw0/jobfit-model | SmolLM2-135M + LoRA, scored via `lm_head` | [F] (GitHub) | Code AGPL-3.0-or-later [F] | n/a | Not a free-text generator | **Reference-only** |
| TinyLlama-1.1B, Llama-3.2-1B, Gemma-3-1B, Qwen3-1.7B, Qwen3-4B | >= 1B | name/size | n/a | n/a | n/a | **Excluded** |

## Per-model notes

### 1. Qwen/Qwen3-0.6B

- Params: 0.6B total, 0.44B non-embedding [S] (search summary of Qwen3-0.6B card mirrors, e.g.
  https://huggingface.co/aoiandroid/Qwen3-0.6B). Official card not fetched.
- Architecture [S]: 28 layers, GQA 16 Q / 8 KV heads, head_dim 128, hidden_size 1024,
  intermediate_size 3072, vocab_size 151936, `tie_word_embeddings: true`
  (search summaries citing https://huggingface.co/keras/qwen3_0.6b_en/blob/main/README.md and
  https://huggingface.co/CodeAtCMU/Qwen3-0.6B-Base_full_sft_JavaScript_data_12K/commit/b9617cbc8dd32df72dd76556eabe5f861a3c04b7).
- Total [C]: embeddings 155,582,464 + 28 x 15,730,944 per layer + final norm 1,024 = **596,049,920**.
  Tied embeddings, so the LM head adds 0. Well under 1B.
- Context: 32,768 per card [S]. `max_position_embeddings` in the official config: UNVERIFIED —
  could not fetch (search found 32768 in Base copies, 40960 not confirmed).
- License: "All our open-weight models are licensed under Apache 2.0." [F] https://github.com/QwenLM/Qwen3
- Min transformers: `transformers>=4.51.0`. Older gives `KeyError: 'qwen3'`. [F] https://github.com/QwenLM/Qwen3
- Thinking toggle: on by default. `tokenizer.apply_chat_template(..., enable_thinking=False)` strictly
  disables it. `/think` and `/no_think` soft switches also exist. [F] https://github.com/QwenLM/Qwen3
- Decoding: thinking mode T=0.6, top_p=0.95, top_k=20, min_p=0, no greedy [S].
  Non-thinking mode: T=0.7 confirmed [S]; top_p=0.8, top_k=20, min_p=0 are the commonly quoted
  values but are UNVERIFIED — could not fetch. `presence_penalty` 1.5 only as a repetition remedy [S].
- Matcher note: always pass `enable_thinking=False`. Otherwise `<think>` text breaks strict JSON
  and burns CPU tokens.

### 2. Qwen/Qwen2.5-0.5B-Instruct

- Params: 0.49B total, 0.36B non-embedding [S] (search summary citing
  https://huggingface.co/Mozilla/Qwen2.5-0.5B-Instruct-llamafile and promptlayer: 494M / 360M).
- Architecture [S]: 24 layers, GQA 14 Q / 2 KV heads, hidden_size 896, intermediate_size 4864,
  vocab_size 151936, `tie_word_embeddings: true` (copy at
  https://huggingface.co/llmware/qwen2.5-0.5b-instruct-ov/blob/0f06b9bc1ce1b93e2f491579e4aea6043abd0c3d/config.json).
- Total [C]: embeddings 136,134,656 + 24 x 14,912,384 (incl. QKV bias) + 896 = **494,032,768**.
  Matches the 494M figure.
- Context: 32,768 full, 8,192 generation [S]. The 128K claim is the larger Qwen2.5 sizes, not 0.5B.
- License: Apache-2.0 [S] (https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/blob/main/LICENSE).
- Min transformers: UNVERIFIED — could not fetch the card. Qwen2 arch is in transformers since 4.37;
  the card's exact statement was not seen.
- No thinking mode. Decoding defaults (`generation_config.json`): UNVERIFIED — could not fetch.
  For strict JSON, greedy (`do_sample=False`) is the sane first setting; benchmark will confirm.

### 3. Kus-hal/resume-screener-lora

- `adapter_config.json` and README: **UNVERIFIED — could not fetch**
  (https://huggingface.co/Kus-hal/resume-screener-lora/raw/main/adapter_config.json, ENOTFOUND).
- What the search summary of the card says [S] (https://huggingface.co/Kus-hal/resume-screener-lora):
  - LoRA adapter on **Qwen/Qwen2.5-0.5B-Instruct**, loaded with PEFT on that base.
  - r=16, lora_alpha=32, lora_dropout=0.05, target modules q/k/v/o projections.
  - Data: 800 train / 96 eval examples. Source of the data: UNVERIFIED.
  - 3 epochs on a free Colab T4. Val loss 0.2784 (epoch 1) to 0.1714 (epoch 3).
  - Purpose: structured JSON resume-screening verdicts instead of free prose.
- UNVERIFIED — could not fetch: exact `base_model_name_or_path` string, `task_type`, PEFT version,
  the exact JSON schema it emits, license, and whether `adapter_model.safetensors` exists.
- Is it a genuine LoRA? The card describes a PEFT LoRA [S], not a merged full model. File list not seen.
- Compatibility verdict with Qwen/Qwen2.5-0.5B-Instruct: **likely compatible** (same base per card).
  Total stays ~494M + a few M adapter params, so still < 1B.
- Fit to our task: **partial at best**. It was trained for a whole-resume verdict, not per-requirement
  MET/MISSING/UNCERTAIN with verbatim evidence. Its schema will likely fight our prompt.
  Treat as an experiment arm, never as the default.
- Before use, on the laptop: open `adapter_config.json`, confirm `base_model_name_or_path`
  is `Qwen/Qwen2.5-0.5B-Instruct`, `peft_type: LORA`, weights file present, and a license exists.
  No license = do not ship it.

### 4. gw0/jobfit-model (reference baseline only)

- Source [F]: https://github.com/gw0/jobfit-model ("A CV/job-post fit-scoring decision model, training
  pipeline, and web app").
- Base: SmolLM2-135M-Instruct fine-tuned with LoRA. Causal LM, but used as a **typed-decision scorer**:
  17 fixed JobFit questions per CV/job pair, each answered with a 5-level score + calibrated confidence,
  read from `lm_head` in one masked forward pass. It does not generate free text or evidence quotes.
- Ships as int8 ONNX (136.6 MB) for transformers.js in the browser. Repo ships no weights.
- Metrics (mean MAE, 17 questions, 500 test pairs): fine-tuned 0.1545, quantized 0.1568,
  keyword baseline 0.1961, train-mean 0.2046, zero-shot base 0.3063.
- License: code AGPL-3.0-or-later; weights inherit base model license [F].
  Benchmark corpus gw0/jobfit-jevbench is AGPL-3.0 [S] (https://github.com/gw0/jobfit-jevbench).
- Verdict: **reference-only**. Wrong output contract (scores, not JSON with quotes). AGPL code must
  not be copied into HireSignal without a license decision.

### 5. Other sub-1B instruct models

- **HuggingFaceTB/SmolLM2-360M-Instruct**: ~362M params [S]; Apache-2.0 [S] (repo license Apache-2.0 [F]
  https://github.com/huggingface/smollm). Context UNVERIFIED (8k suspected from a checkpoint name).
  Weak on long CV prompts if context is 8k; still a fast CPU baseline.
- **LiquidAI/LFM2-350M / LFM2-700M**: 354,483,968 / 742,489,344 params, 32,768 ctx,
  LFM Open License v1.0 [S] (https://huggingface.co/LiquidAI/LFM2-1.2B card table).
  The LFM license is not Apache; it has commercial terms. Read it before any commercial use.
  Needs a recent transformers (exact version UNVERIFIED).
- **google/gemma-3-270m-it**: ~268-270M total, ~170M of it embeddings (262k vocab), ~100M in
  transformer blocks, 32K context, Gemma Terms of Use [S] (search summaries, official card not fetched).
  Very little compute for reasoning; likely poor at evidence extraction. Low priority.

### 6. Excluded (>= 1B total params)

- TinyLlama-1.1B: 1.1B. Over the limit.
- Llama-3.2-1B: ~1.2B with embeddings. Over the limit.
- Gemma-3-1B: ~1B. Not strictly below 1B.
- Qwen3-1.7B: 1.7B. Over the limit.
- LFM2-1.2B: 1.2B. Over the limit.
- Qwen3-4B / Ollama 4B: 4B. Over the limit, and that architecture is **CANCELLED**.

## Recommended benchmark order (CPU-only budget)

1. **Qwen/Qwen2.5-0.5B-Instruct** (base, no adapter). Smallest strong ChatML model, no thinking
   overhead, good JSON following per its card. Run first as the baseline.
2. **Qwen/Qwen2.5-0.5B-Instruct + Kus-hal/resume-screener-lora**. Same base, so it is a cheap
   A/B. Only after the adapter files and license are verified on the laptop.
3. **Qwen/Qwen3-0.6B** with `enable_thinking=False`. Likely better reasoning; ~20% more params.
4. **HuggingFaceTB/SmolLM2-360M-Instruct**. Speed floor. Drop it if JSON validity is poor.

Score each arm on: JSON validity rate, decision accuracy vs. gold labels, evidence quotes that are
verbatim substrings of the CV, seconds per requirement on the 4-core CPU, peak RAM.
Pick ONE model for production. LFM2 and Gemma-3-270m only if all three base models fail.
