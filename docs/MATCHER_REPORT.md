# HireSignal Matcher Agent: architecture, decisions, evaluation

Branch `claude/kind-albattani-k7qlt9`. Written 2026-10-15 for the final project report. Every number
in this document comes from a file in `benchmark/results/` or another file named next to it. Anything
argued but not measured is labelled **reasoned**.

## 1. Task

For each requirement of a job, the Matcher reads an anonymized CV and the requirement and returns:
- a decision `MET`, `MISSING` or `UNCERTAIN`;
- a basis `supported`, `contradicted`, `not_documented` or `ambiguous`;
- verbatim CV evidence with character offsets;
- an explanation;
- the ESCO references used;
- a human-review flag with its reasons.

It never rejects a candidate and never produces a hiring decision (`MatchSummary.note`).

## 2. Architecture

```
anonymized CV (text)      structured job requirements
        │                          │
        │                 knowledge lookup: team RAG, BM25 over 1,621 ESCO concepts
        │                 (query = requirement skill terms only; CV text never sent)
        └──────────┬───────────────┘
                   ▼
       prompt (matcher/prompt.py, one format for inference, benchmark and LoRA)
                   ▼
   ONE generative SLM < 1B params (+ optional LoRA adapter of the same base)
                   ▼
   deterministic Python validation (matcher/validate.py)
     JSON + schema parse │ exact-substring quote check │ decision/basis consistency │
     years-of-experience check │ review flags
                   ▼
   RequirementResult × n  →  MatchReport (strict Pydantic / JSON Schema, matcher/json_schemas/)
```

| Module | Role |
|---|---|
| `matcher/schemas.py` | Data contracts (CV, Job, Requirement, KnowledgeRef, ModelAnswer, RequirementResult, MatchReport); `extra="forbid"` everywhere |
| `matcher/prompt.py` | System + user message; knowledge is labelled "terminology only, NOT evidence" |
| `matcher/knowledge.py` | `RagKnowledge` (team `rag/retrieval.py`, BM25 mode), `FixtureKnowledge`, `NoKnowledge` |
| `matcher/backends.py` | `TransformersBackend` (the SLM; refuses ≥ 1B params; refuses adapters whose `adapter_config.json` names another base), `LexicalBaseline` (non-neural reference), `MockBackend` (tests only) |
| `matcher/validate.py` | The rules in §4 |
| `matcher/agent.py` | Orchestration and summary (counts, must-have coverage ratio) |
| `benchmark/` | Synthetic dataset generator, locked splits, metrics, resumable runner, comparison table, RAG check |
| `finetune/` | SFT builder (refuses test split), resumable LoRA trainer, smoke test |

### One-generative-model constraint (verified)

- Only `TransformersBackend` loads a neural network. Its parameter guard counts `model.parameters()`
  and raises an error at ≥ 1,000,000,000.
- A LoRA adapter only adds low-rank matrices to that same base. The compatibility check
  refuses any other base.
- Retrieval uses `Retriever(chunks)` with `model=None`, which is BM25 only. The RAG branch's optional
  e5 embedder and cross-encoder reranker are never loaded. The test
  `test_end_to_end_with_real_rag_bm25_and_mock_slm` asserts this: `retriever.model is None`, and
  neither `sentence_transformers` nor `qdrant_client` is imported.
- Python does the scoring and validation. Python and the BM25 index are tools, not models.

Measured parameter counts (sum of `model.parameters()` at load time, recorded in each run's `config.json`):
see the results table in §6.

## 3. Decisions and alternatives

| # | Decision | Alternatives considered | Why | Status |
|---|---|---|---|---|
| M1 | One SLM < 1B, CPU-capable | Qwen3-4B via Ollama (cancelled by the project); two-model pipelines (embedder + generator) | Project constraint; runs on a laptop GPU (6 GB) and on CPU | constraint |
| M2 | Lexical BM25 retrieval of ESCO inside the Matcher | e5-small dense (RAG default profile), hybrid RRF, cross-encoder | A dense model would be a second neural model. BM25 found the right ESCO concept for 100 % of the val alias items (§6.3) | measured |
| M3 | One SLM call per requirement | One call per job with all requirements | Short contexts suit 0.5B models (prompt ≤ 605 tokens); a malformed answer affects one requirement only | reasoned |
| M4 | The model proposes, Python decides | Trust model output | Tiny models hallucinate quotes (seen in the first smoke run: the model quoted ESCO text and its own paraphrases as "CV evidence") | measured |
| M5 | Exact substring evidence only (after stripping surrounding whitespace) | Fuzzy matching | Fuzzy matching would accept paraphrases, which are fabricated evidence | reasoned |
| M6 | `MISSING` split into `contradicted` vs `not_documented` | One MISSING class | "Not mentioned" is not proof of absence; must-have `not_documented` always goes to human review | requirement |
| M7 | Review priority low/medium/high from named rules | Model-reported confidence | Model confidences are uncalibrated. Rule reasons are auditable. Never presented as probabilities | reasoned |
| M8 | Greedy decoding, `max_new_tokens=192`, same prompt for every model | Sampling; per-model prompts | Comparability and reproducibility | design |
| M9 | Qwen3 with `enable_thinking=False` | Thinking mode | The JSON-only answer must fit 192 tokens; thinking output would be cut | reasoned |
| M10 | Synthetic benchmark with split-disjoint pools | Real CVs | No private data may be used. Disjoint pools prevent memorising phrasings across splits | design |
| M11 | Test split locked (runner flag, SFT refusal ×3) | Free use | Model selection on val only | design |
| M12 | RAG used read-only from its branch via `HIRESIGNAL_RAG_DIR` | Merge the RAG branch | Merging was not authorised in this environment; the code is not duplicated | constraint |

## 4. Validation rules (`matcher/validate.py`)

| Rule | Effect | Review priority |
|---|---|---|
| Output not parseable as `ModelAnswer` JSON | `UNCERTAIN`/`ambiguous` | high |
| Decision and basis inconsistent (e.g. MET + not_documented) | `UNCERTAIN` | high |
| Quote not an exact CV substring | quote dropped | medium |
| `MET` with no verified quote | `UNCERTAIN` | high |
| `MET` on a `min_years` requirement, years in quotes < minimum | `UNCERTAIN` | high |
| `MET` on `min_years`, no duration parseable | kept, flagged | medium |
| `MISSING`/contradicted without a verified quote | becomes `not_documented` | medium |
| `MET` on a skill whose quote contains no requirement term or ESCO alias | kept, flagged (semantic inference) | medium |
| Any `UNCERTAIN` | flagged | medium |
| Must-have `MISSING` | flagged (no automatic rejection) | medium |

Years parsing covers explicit "N years" and merged date ranges ("2019 - present", reference year 2026).

Because evidence is accepted only after verification, a quote of ESCO text can never count as candidate evidence.
`test_knowledge_text_cannot_be_evidence` checks this.

## 5. Benchmark

### 5.1 Data (`benchmark/make_dataset.py`, version `bench-v1`, seed 20261015)

The data is fully synthetic and anonymized. It contains no names, e-mails or employers. Every gold quote
is asserted to be an exact CV substring. Counts are from `benchmark/data/MANIFEST.json`:

| split | cases | requirements | MET / MISSING / UNCERTAIN | sha256 (prefix) |
|---|---|---|---|---|
| train | 150 | 681 | 305 / 273 / 103 | d0206264f093 |
| val | 45 | 202 | 86 / 77 / 39 | 37c60915f2db |
| test (LOCKED) | 45 | 199 | 92 / 84 / 23 | 0bde3a86cc30 |

The data includes these hard cases, tagged per requirement (counts in the manifest):
- ESCO alias equivalence: the requirement uses the ESCO preferred label and the CV only an alternative label;
- implicit project evidence;
- missing evidence;
- contradiction and negation traps ("Has not worked with X", "preparing for the X exam");
- insufficient experience;
- ambiguous duration;
- partial evidence;
- RAG near-miss: ESCO retrieves the required concept, but the CV shows only a neighbouring activity;
- distractor details;
- multi-requirement jobs (3–6 requirements).

Leakage control: every pool is partitioned by index into the three splits. The pools are skills, ESCO pairs,
project sentences, requirement and CV phrasings, section titles and headers. `benchmark/tests` checks that
no CV text, no requirement sentence and no CV line longer than 25 characters is shared across splits.

**Label policy** (debatable cases; a reviewer may disagree):
- "Some familiarity with X" against "Experience with X" is `UNCERTAIN`.
- "Preparing for certificate X" is `MISSING`/contradicted.
- A bachelor's degree in an unrelated field against a master's requirement is `MISSING`/contradicted.

### 5.2 Metrics (`benchmark/metrics.py`)

- **Final**: macro-F1, accuracy, per-class P/R/F1 and confusion after validation.
- **Raw**: the same metrics on the model's own decision before validation. An unparseable answer counts as wrong.
- **False-MET rate** = predicted MET among items whose gold is not MET, divided by the number of those items.
- **JSON/schema validity** = share of answers that parse as `ModelAnswer`.
- **Raw quote validity** = share of model quotes that are exact CV substrings.
- **Evidence attribution** = share of correctly decided MET/contradicted items whose verified quote overlaps
  the gold span.
- **Other**: basis accuracy, per-tag accuracy, review rate, latency p50/p95, peak RSS and load time.

## 6. Results

Status: the campaign was **stopped on 2026-10-15 at ~11:00 UTC by the project owner** (change of architecture).
All numbers: val split, 202 requirements, BM25 ESCO RAG (k=3), identical prompt `p1`, greedy decoding,
`max_new_tokens=192`, float32, 4-core cloud CPU. Full table: `benchmark/results/CONSOLIDATED_val.md`.

| run | params | macro-F1 final | macro-F1 raw | false-MET final | false-MET raw | JSON valid | raw quote valid | UNCERTAIN rate | p50 s/req |
|---|---|---|---|---|---|---|---|---|---|
| MOCK gold (pipeline sanity check, not a model) | 0 | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 | 0.193 | 0.00 |
| lexical keyword baseline + RAG (no neural model) | 0 | **0.436** | 0.436 | 0.560 | 0.560 | 1.000 | 1.000 | 0.000 | 0.00 |
| lexical keyword baseline, no RAG | 0 | 0.373 | 0.373 | 0.560 | 0.560 | 1.000 | 1.000 | 0.000 | 0.00 |
| Qwen2.5-0.5B-Instruct + `schema_repair` adapter (post-hoc) | 494,032,768 | 0.265 | 0.386 | 0.009 | — | 1.000 | 0.067 | 0.460 | 5.97 |
| Qwen2.5-0.5B + Kus-hal LoRA + `schema_repair` (post-hoc) | 494,032,768 + LoRA | 0.245 | 0.226 | 0.000 | — | 0.926 | 0.543 | 0.554 | 9.41 |
| Qwen3-0.6B (non-thinking) | 596,049,920 | 0.222 | 0.122 | 0.000 | — | 0.203 | n/a | 0.906 | 10.23 |
| Qwen2.5-0.5B-Instruct | 494,032,768 | 0.211 | 0.265 | 0.009 | 0.276 | 0.634 | 0.056 | 0.698 | 5.97 |
| Qwen2.5-0.5B + `Kus-hal/resume-screener-lora` | 494,032,768 + LoRA | 0.116 | 0.008 | 0.000 | — | 0.030 | 0.889 | 0.970 | 9.41 |
| SmolLM2-360M-Instruct | 361,821,120 | 0.108 | 0.000 | 0.000 | — | 0.000 | n/a | 1.000 | 6.40 |

(The Kus-hal parameter count is the base measured before the adapter was attached. Its model card gives 2,162,688
LoRA parameters. "—" = see `metrics.json`. Raw false-MET is meaningful only when the JSON parses.)

### 6.1 Findings

1. **No zero-shot sub-1B model beats the non-neural keyword baseline** (0.436). The best is 0.265: Qwen2.5-0.5B
   with the deterministic schema repair applied.
2. **Formatting is the first failure mode.** JSON validity ranges from 0 % (SmolLM2-360M) to 63 % (Qwen2.5-0.5B)
   with the strict schema.
3. **Evidence grounding is the second.** When Qwen2.5-0.5B quotes, only 5.6–6.7 % of its quotes are exact CV text.
4. **The validator is what keeps false-MET low.** Qwen2.5-0.5B: raw false-MET 27.6 %, final 0.9 %. The price is
   that most decisions become UNCERTAIN (UNCERTAIN rate 0.46–1.0 against a gold share of 0.193), so they go to
   human review.
5. **The keyword baseline has the opposite failure:** false-MET 56 %. It matches terms in negated sentences,
   and ESCO aliases add recall but not precision.
6. **Kus-hal LoRA (`Kus-hal/resume-screener-lora`, verified PEFT LoRA r=16 on Qwen2.5-0.5B-Instruct, MIT).**
   - It tries our JSON keys in 202/202 answers. It invents labels (`CONTRADIZED`, `NOT_DOCUMENTED`,
     `CHALLENGE|contradicted|…`), adds keys and chains several objects. Its native ATS format appears in only 6/202.
   - A deterministic repair adapter (`matcher/output_adapters.py`, which never adds evidence or decisions) lifts its
     JSON validity from 3.0 % to 92.6 % and its macro-F1 from 0.116 to 0.245.
   - The same adapter lifts the untuned base from 0.211 to 0.265, with raw 0.386 against 0.226 for the adapter.
   - Conclusion: **its weakness is both formatting and reasoning.** After format repair it is still below its own
     base. **Rejected** on this evidence.
   - Not run (campaign stopped): native-prompt, constrained-decoding and one-shot variants (`scripts/kushal_study.sh`).

### 6.2 Not completed (stopped by the owner)

| run | state |
|---|---|
| SmolLM2-135M-Instruct | partial: 186/202 predictions saved, no metrics |
| FLAN-T5-small, resume-scorer-t5-small | not run. Smoke run (6 requirements): 0 % JSON validity, because the T5 vocabulary has no `{`/`}` |
| FERMI-0.8B (decision-only classifier), Qwen3.5-0.8B | not run |
| Kus-hal study variants | not run |
| `gw0/jobfit-model` | not runnable for this task (ONNX-only typed scorer with 17 fixed questions) |

### 6.3 External reference (different data, another session)

Branch `claude/vigilant-albattani-dmn3pk` used a handwritten val set of 110 requirements. Its best zero-shot result
was Qwen3.5-0.8B at 0.486. A CPU pilot LoRA on Qwen2.5-0.5B reached 0.629 on val and 0.563 on the locked test
(false-MET 1.7 %). The two datasets differ, so the numbers are not comparable. They point the same way: sub-1B models
need task fine-tuning to be useful for this task.


## 7. Limitations

- The benchmark is synthetic and template-based. Real CVs are longer, messier and multilingual.
  Numbers measure behaviour on controlled hard cases, not production accuracy.
- Gold labels were written by the generator's label policy (§5.1) and have not been reviewed by a second person.
- The RAG check queries ESCO labels that occur in the requirement text, which is an easy case. Natural-language
  retrieval quality is covered by the RAG team's own evaluation on its branch (exp02/exp03), not here.
- O*NET is not in the repository. Only the ESCO ICT subset (v1.1.x, CC BY 4.0) is used.
- CPU latency was measured on a shared 4-core cloud container; tokenisation jobs ran in parallel for a
  few minutes during the first run. Treat latency as indicative.
- `review_priority` is a rule signal, not a calibrated probability.
- No HireSignal LoRA adapter has been trained (`finetune/README.md`).
- The existing adapter `Kus-hal/resume-screener-lora` was trained for a different output format, a whole-resume
  verdict. It is measured as-is with our prompt.
- The local components `hiresignal_cv_reader`, `hiresignal_benchmark` and `hiresignal_finetune` were not
  accessible. The integration contract is in `LOCAL_INTEGRATION_HANDOFF.md`.

## 8. Final architecture evaluation (Qwen3-4B Matcher → Validator → Bias Auditor → NLI Judge), validation split only

**Validation-only results.** The sealed test split (199 requirements) has not been run; it is reserved for one
confirmation run of the chosen configuration.

**Setup.**
- 202 val requirements. Same prompt `p1`, greedy decoding, `max_new_tokens=192`.
- Matcher: `Qwen/Qwen3-4B-Instruct-2507`, served as GGUF Q4_K_M (`unsloth/Qwen3-4B-Instruct-2507-GGUF@a06e946b`) through
  llama.cpp 0.3.16 on 4 CPU cores. Calls go through the OpenAI-compatible backend (`matcher/backends_api.py`).
- Hosted API: **not tested**, because no credentials were available.
- Hardware and versions are recorded in each `config.json`.

### 8.1 Matcher

| configuration | macro-F1 final | macro-F1 raw | false-MET final | MET P / R | JSON valid | quote valid | p50 s/req |
|---|---|---|---|---|---|---|---|
| lexical baseline + RAG (no model) | 0.436 | 0.436 | 0.560 | 0.508 / 0.779 | 1.000 | 1.000 | 0.00 |
| Qwen3-4B, no RAG | **0.634** | 0.641 | **0.009** | — | 0.950 | — | 12.9 |
| Qwen3-4B + BM25 RAG | 0.630 | 0.647 | **0.009** | 0.981 / 0.605 | 0.916 | 1.000 (141/141) | 16.4 |

- Qwen3-4B + RAG: evidence attribution to the gold span is 0.855, and the validator changed 9.4 % of decisions.
- Raw false-MET with RAG is 0.026; the validator cuts it to 0.009.
- Main weakness: UNCERTAIN is over-predicted. UNCERTAIN precision is 0.343 at recall 0.897, so about 50 % of answers are
  UNCERTAIN against a gold share of 19 %.

**RAG ablation (per tag, accuracy with RAG vs without):**

| tag | with RAG | without RAG |
|---|---|---|
| alias equivalence | 0.571 | 0.286 |
| implicit project evidence | 0.400 | 0.600 |
| RAG near-miss | 0.364 | 0.455 |

The net effect is zero: 7 requirements are correct only with RAG and 8 only without, which is not significant. RAG
helps exactly the case it targets (ESCO aliases) and distracts on others. **Keep RAG only together with a fix for the
distraction**, for example retrieving only when the requirement contains an ESCO label. This is a recommendation, not
yet measured.

### 8.2 Bias Auditor (counterfactual, 30 val requirements × 4 attributes × 2 variants = 240 Matcher calls)

| matcher | flagged requirements | name | gender | nationality | age |
|---|---|---|---|---|---|
| Qwen3-4B + RAG | 1/30 (3.3 %) | 3.3 % | 0 | 0 | 0 |
| known-bias mock (control) | 21/30 (70 %; every requirement where a flip was possible) | 0 | 0 | 70 % | 70 % |
| lexical baseline (unbiased control) | 0/30 (false-positive check) | 0 | 0 | 0 | 0 |

- The single Qwen flip was on `val-039 r1`: UNCERTAIN for "Emily Johnson" and MET for "Mohamed Ben Salah".
- It is a borderline case. With n = 30 there is no evidence of systematic bias. The case is flagged for human review,
  as designed.

### 8.3 NLI Judge (`MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`, 184M) — error detection on Matcher decisions

The Judge only flags; it never changes a decision. Thresholds were calibrated on train-dev only: pretrained τ = 0.65,
fine-tuned τ = 0.85.

**Fine-tuning.**
- Data: 770 NLI pairs from the train split; train-dev has 208 pairs.
- Config: 2 epochs, lr 2e-5, batch 16, fp32 on CPU, 10.3 min.
- Train-dev accuracy went from 0.587 to 0.990. This is optimistic: train-dev comes from the same templates.

**Incident.** The first fine-tuning run loaded the checkpoint in float16, because its config says so and
transformers 5 honours it. The loss went NaN at step 12, at about 8 min per step. The run was stopped, fp32 was
forced, and everything was re-run. The fp16 artefacts are kept in `benchmark/results/judge/_invalid_fp16/`.

| decisions judged | Judge | flag precision | flag recall | F1 | false-flag rate on correct | AUROC | ECE |
|---|---|---|---|---|---|---|---|
| lexical baseline (84 errors / 202) | pretrained | 0.652 | 0.714 | 0.682 | 0.271 | 0.716 | 0.250 |
| lexical baseline | **fine-tuned** | **0.894** | 0.702 | **0.787** | **0.059** | **0.905** | 0.151 |
| Qwen3-4B + RAG (8 errors / 100 applicable) | pretrained | 0.106 | 0.625 | 0.182 | 0.457 | 0.438 | — |
| Qwen3-4B + RAG | **fine-tuned** | **0.500** | 0.375 | **0.429** | **0.033** | 0.413 | 0.192 |
| Qwen3-4B no RAG (8 errors) | fine-tuned | 0.375 | 0.375 | 0.375 | 0.053 | 0.537 | — |

- On the lexical baseline, the pretrained Judge caught all 22 negation-trap errors and all 26 contradiction errors.
- On Qwen3-4B, the fine-tuned Judge misses alias and duration errors.
- Only 8 Qwen errors were judged, so the Qwen confidence intervals are very wide.

### 8.4 System: what a human must review, and what passes unreviewed

A requirement **passes without review** only if all of these hold:
- the validator raised no reason;
- the decision is not UNCERTAIN;
- the Judge verdict is PASS;
- there is no bias flag.

| matcher | stages | review rate | passes unreviewed | wrong among passed | false-MET among passed |
|---|---|---|---|---|---|
| lexical baseline | validator only | 0.381 | 125 | 48 | 44 |
| lexical baseline | + fine-tuned Judge | 0.639 | 73 | 8 | 4 |
| Qwen3-4B + RAG | validator only | 0.743 | 52 | 1 | 0 |
| Qwen3-4B + RAG | + pretrained Judge | 0.970 | 6 | 0 | 0 |
| Qwen3-4B + RAG | + fine-tuned Judge | 0.807 | 39 | 1 | 0 |

**Conclusions.**
1. **The Matcher is the step change.** Qwen3-4B more than doubles the best sub-1B result (0.634 vs 0.265) and beats
   the lexical baseline (0.436), with 0.9 % false-MET and 100 % verbatim quotes. It is not yet production-ready: the
   high UNCERTAIN rate gives a 74 % review rate, and the data is synthetic.
2. **The Judge is valuable when the Matcher makes obvious errors.** With the lexical baseline, unreviewed false-METs
   drop from 44 to 4.
3. **Behind Qwen3-4B the Judge adds review load without removing an error.** One error passes either way, and 13 more
   requirements go to review. Qwen's remaining errors are subtle (aliases, durations), where an NLI model trained on
   template data does not generalise.
4. **Recommendation:**
   - Keep the fine-tuned Judge as a low-noise safety net (3.3 % false flags) for the hosted Matcher. A model or provider
     change could reintroduce gross errors.
   - Do not count it as an accuracy gain.
   - The priority next step is reducing Qwen's UNCERTAIN over-prediction. Options: the teammate's QLoRA run on the
     train split, or a prompt fix.
5. **Bias:** no systematic counterfactual effect was detected on 30 requirements. The auditor detects an injected bias
   and raises no false alarms.

Reproduce:
- matcher runs: `scripts/hs_queue.sh` with the llama.cpp server (`scripts/run_qwen4b.sh` header);
- per-stage logs: `benchmark/results/logs/queue/`;
- Judge checkpoint: `/home/user/judge_runs/deberta-hs-v1/best` (not in git, ~0.7 GB). Rebuild it with
  `python -m finetune.train_judge --out <dir>`; the training record is `benchmark/results/judge/finetuned_train_meta.json`.
