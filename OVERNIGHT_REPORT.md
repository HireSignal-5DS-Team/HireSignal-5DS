# HireSignal Matcher: overnight report (2026-10-14 23:39 to 2026-10-15 UTC)

Branch: `claude/vigilant-albattani-dmn3pk`. `main` and `claude/kind-albattani-k7qlt9` untouched. No PR opened.

## Result in one paragraph

The Matcher runs end to end with one generative model under 1B parameters: **Qwen/Qwen2.5-0.5B-Instruct
(494,032,768 params) + a task LoRA trained here (r=16, +8.8M params)**, BM25 ESCO retrieval, and deterministic
validation. On the validation set (110 requirements), it reaches macro-F1 **0.629** with a false-MET rate of
**8.3%**, against 0.486 / 21.7% for the best zero-shot model (Qwen3.5-0.8B) and 0.507 / 20.0% for a keyword
baseline. On the locked test set, run once after selection: TEST_RESULT. The LoRA is a CPU **pilot**
(100-step budget, stopped at step 98 by the 2-hour job limit; `best/` = step 75). Training and evaluation data are synthetic, so
these numbers show the pipeline works and how arms rank. They are not production accuracy.

## COMPLETE AND VERIFIED

- Recovery of `e584a13` (matcher) and `1f5610b` (RAG) into this branch; `docs/RECOVERY_REPORT.md`.
- Hugging Face access works: API, config files and weights (`huggingface.co` redirects to `us.aws.cdn.hf.co`, Xet bridge).
  `download.pytorch.org` is blocked; PyPI torch 2.14.1 works instead. No HF hostname is missing.
- Matcher: schemas, prompt p2, strict JSON parsing, verbatim evidence (stored as exact CV slices with spans),
  negation, duration and term checks, review flags (`docs/MATCHER.md`).
- Benchmark data v1 (`benchmark/CONTRACT.md`, `benchmark/LABELING.md`): handwritten val (14 CVs, 110 reqs) and
  locked test (14 CVs, 112 reqs), generated train (300 CVs, 1,552 reqs, seed 13). `check_data.py`: 0 errors, no CV
  text shared across splits. Test was read only by `check_data.py` and the single final run.
- Model audit re-verified on the Hub with pinned revisions and exact local param counts (`docs/MODEL_AUDIT.md`,
  `models/candidates.json`).
- Val benchmark of 8 SLM arms + Kus-hal adapter + pilot LoRA + keyword baseline (table below; `benchmark/results/`).
- LoRA pilot trained on CPU on the train split only; adapter committed: `finetune/runs/qwen25_05b_lora_pilot/best/`.
- Tests: `python -m pytest -q matcher benchmark finetune rag/tests/test_rag.py` -> 52 passed. These use mock,
  lexical and tiny random models; the real-model evidence is the benchmark runs.

## Val results (n=110, final = after validation)

| arm | params | macro-F1 | acc | false-MET | raw JSON valid | raw quote verbatim | s/req (CPU 4 cores) | RSS MB |
|---|---|---|---|---|---|---|---|---|
| **Qwen2.5-0.5B + pilot LoRA + RAG (selected)** | 503M | **0.629** | 0.655 | **8.3%** | 99.1% | 86.8% | 6.8 | 3,624 |
| Qwen2.5-0.5B + pilot LoRA, no RAG | 503M | 0.629 | 0.655 | 8.3% | 99.1% | 86.7% | 6.2 | 3,620 |
| keyword baseline + RAG (no neural model) | 0 | 0.507 | 0.545 | 20.0% | 100% | 100% | 0.001 | 53 |
| keyword baseline, no RAG | 0 | 0.488 | 0.527 | 13.3% | 100% | 100% | 0.000 | 26 |
| Qwen3.5-0.8B zero-shot + RAG | 752M | 0.486 | 0.618 | 21.7% | 99.1% | 84.8% | 15.3 | 5,408 |
| Qwen3-0.6B zero-shot + RAG | 596M | 0.272 | 0.300 | 1.7% | 62.7% | 88.9% | 9.7 | 5,106 |
| LFM2.5-350M zero-shot + RAG | 354M | 0.259 | 0.273 | 8.3% | 30.0% | 100% | 4.9 | 2,796 |
| Qwen2.5-0.5B + Kus-hal/resume-screener-lora + RAG | 496M | 0.256 | 0.300 | 0.0% | 54.5% | 74.7% | 8.0 | 3,625 |
| Qwen2.5-0.5B zero-shot + RAG | 494M | 0.248 | 0.291 | 0.0% | 83.6% | 100% | 5.2 | 3,623 |
| SmolLM2-360M zero-shot + RAG | 362M | 0.236 | 0.300 | 55.0% | 63.6% | 82.4% | 9.4 | 2,798 |
| Granite-4.0-350M zero-shot + RAG | 352M | 0.115 | 0.209 | 0.0% | 0.9% | n/a | 6.9 | 2,814 |
| LFM2-350M zero-shot + RAG | 354M | 0.115 | 0.209 | 0.0% | 0.0% | n/a | 7.9 | 2,789 |

Selected pilot per class (val): MET P 0.87 / R 0.66, MISSING P 0.63 / R 0.73, UNCERTAIN P 0.41 / R 0.52.
Weak tags: experience_years 0.17, language 0.29, negation 0.50, education 0.56.

Findings:
- The existing Kus-hal adapter is not better than its base on this task: macro-F1 0.256 vs 0.248, and JSON
  validity is lower (54.5% vs 83.6%). It was trained for whole-resume ATS scores, not per-requirement evidence.
- RAG contribution: none measurable on val for the selected model (0.629 with and without), and +0.019 for the
  keyword baseline at the cost of more false METs. ESCO refs are still attached to results for reviewers and used
  for alias-aware term checks. The val set has only 6 RAG-dependent items, so this is weak evidence either way.
- Zero-shot sub-1B models almost never answer UNCERTAIN; the LoRA fixed that (UNCERTAIN recall 0.05 -> 0.52).
- The validator lowers the pilot's raw macro-F1 (0.657 -> 0.629); all 3 changed items were correct demotions
  (quote not in the CV, MET without duration evidence).

## Locked test (single run, after selection)

TEST_TABLE

## IMPLEMENTED BUT NOT FULLY TESTED

- `Matcher.match()` report assembly with a real model: exercised per requirement by the benchmark, full report
  only with mock backends in tests.
- `RagKnowledge` uses rag/ in BM25 mode only; the RAG branch's dense/hybrid modes are not used (one-neural-model rule).

## PREPARED BUT NOT EXECUTED

- Full LoRA run (`finetune/configs/qwen25_05b.yaml`, 1,408 examples x 2 epochs): ~5-6 h on this CPU, ~15-30 min on a T4.
- Qwen3.5-0.8B LoRA (`finetune/configs/qwen35_08b.yaml`): module names verified, GPU recommended
  (its gated-delta layers fall back to slow reference kernels on CPU).

## BLOCKED WITH DOCUMENTED CAUSE

- Nothing external. Background jobs are capped at 2 hours and the container is reclaimed when the session idles
  (one run was killed at ~01:00 UTC and restarted from its checkpoint).
- google/gemma-3-270m-it is gated; skipped (no token used).
- Windows-only `hiresignal_benchmark`, `hiresignal_finetune`, `hiresignal_cv_reader` are not reachable from the cloud.
  `benchmark/` and `finetune/` here are new implementations; reconcile them with the local folders.

## REMAINING WORK

1. Human review of val/test labels (`benchmark/build_handwritten.py`). QA already fixed 3 val labels for policy consistency.
2. Real (anonymized) CV/job pairs: the current data is synthetic; train data is template-generated and easy (dev loss 0.014).
3. Full LoRA run on a GPU; then compare to the pilot on val only.
4. Weak areas: experience years (0.17 on val), languages, negation. Years are attributed per quote (`shortcut:` in validate.py).
5. LFM2/LFM2.5 license (LFM Open License v1.0, revenue cap) must be cleared before any use; Qwen2.5 is Apache-2.0.
6. Connect the Windows CV reader output to `matcher.schemas.CV` (`text` is the evidence source; `structured` is never evidence).

## Key commits
`ff95436` / `c7fb97b` recovery merges, `0cc4a59` benchmark, `2bae090` finetune, `b4ad04f` model audit,
`408eeac` prompt p2, `b9099c6` QA fixes, `15705e6` pilot adapter, `ccc06e5` val batch 2. Latest: `git log -1`.
