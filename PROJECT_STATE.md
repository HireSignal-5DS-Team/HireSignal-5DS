# PROJECT_STATE (authoritative checkpoint)

Updated: 2026-10-15 04:50 UTC. Branch `claude/vigilant-albattani-dmn3pk`. Latest SHA: see `git log -1`.

## Phase
P7 done for this session. Selected on val: Qwen2.5-0.5B-Instruct + pilot LoRA (`finetune/runs/qwen25_05b_lora_pilot/best`) + BM25 RAG.
Val macro-F1 0.629 / false-MET 8.3%; locked test (single run) 0.563 / 1.7%. Full tables: `OVERNIGHT_REPORT.md`, `benchmark/results/COMPARISON.md`.
The container is reclaimed when the session idles and background jobs are capped at 2 h: use run_in_background, keep jobs < 2 h, rely on resumable runs.

## Done and verified
- Recovery: matcher (`e584a13`) + RAG (`1f5610b`) merged; see `docs/RECOVERY_REPORT.md`.
- Hugging Face: API, file and weight downloads work (`huggingface.co` -> `us.aws.cdn.hf.co` Xet bridge). No blocked HF host.
  `download.pytorch.org` is blocked; torch comes from PyPI instead (2.14.1).
- Benchmark data v1: val 14 cases/110 reqs (handwritten), test 14/112 (handwritten, LOCKED), train 300/1552 (generated, seed 13).
  `python benchmark/check_data.py` -> 0 errors. train.jsonl sha256 `399ef0c3...`.
- Models: 8 sub-1B arms loadable, revisions pinned in `models/candidates.json`; audit `docs/MODEL_AUDIT.md`.
- Tests: `python -m pytest -q matcher benchmark finetune rag/tests/test_rag.py` -> all pass (mock/lexical/tiny-model only).
- Lexical baseline val (no neural model): see `benchmark/results/COMPARISON.md`.
- LoRA pipeline built and smoke-tested (5 steps Qwen2.5-0.5B CPU, adapter reloads through TransformersBackend).

## Exact next action
1. Human review of val/test labels in `benchmark/build_handwritten.py` (then `python benchmark/build_handwritten.py && python benchmark/check_data.py`).
2. Full LoRA on a GPU: `python -m finetune.build_sft benchmark/data/train.jsonl && python -m finetune.train_lora --config finetune/configs/qwen25_05b.yaml --name qwen25_05b_lora`
   then `python benchmark/run.py --split val --backend transformers --arm qwen2.5-0.5b --adapter finetune/runs/qwen25_05b_lora/best --knowledge rag --out benchmark/results/val_qwen2.5-0.5b+full-lora_rag`.
   Compare on val only. The locked test has been used once (TEST_* dirs); do not reuse it for selection.
3. Improve weak tags (experience_years, language, negation) via training data, not test inspection.

## Blockers
- None external. CPU-only (4 cores, 15 GB): full LoRA (1408 ex x 2 epochs) ~5-6 h on CPU; GPU recommended (finetune/README.md).
