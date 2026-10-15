# PROJECT_STATE (authoritative checkpoint)

Updated: 2026-10-15 01:05 UTC. Branch `claude/vigilant-albattani-dmn3pk`. Latest SHA: see `git log -1`.

## Phase
P3 (real experiments) running: `scripts/overnight.sh` (log `logs/overnight.log`, not committed).
IMPORTANT: the cloud container is reclaimed when the session idles (~01:00 UTC restart killed a nohup run).
Launch long jobs as a harness-tracked background Bash task (run_in_background), not nohup.

## Val results so far (n=110, prompt p2, validator as of b9099c6+; rescored from raw)
| arm | acc | macro-F1 | false-MET | UNCERTAIN recall | raw JSON valid | raw quote verbatim | s/req |
|---|---|---|---|---|---|---|---|
| lexical + RAG (no neural model) | 0.545 | 0.507 | 0.200 | see metrics | 1.00 | 1.00 | 0.001 |
| Qwen3.5-0.8B zero-shot + RAG | 0.618 | 0.486 | 0.217 | 0.05 | 0.99 | 0.85 | 15.3 |
Zero-shot models almost never answer UNCERTAIN; this is the main target of the LoRA.

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

## Pipeline stages (scripts/overnight.sh, each resumable)
1. Zero-shot val, RAG: qwen3.5-0.8b, qwen2.5-0.5b, qwen3-0.6b, lfm2.5-350m.
2. LoRA pilot Qwen2.5-0.5B, 100 steps x 8 (`finetune/configs/qwen25_05b_pilot.yaml`), then val eval of `best/`.
3. Val: Kus-hal LoRA (negative control), smollm2-360m, granite-4.0-350m, lfm2-350m; Qwen3.5 without RAG (ablation).

## Exact next action
- If `logs/overnight.log` lacks "done": `nohup bash scripts/overnight.sh > logs/overnight.log 2>&1 &` (resumes).
- Then `python benchmark/compare.py`, pick model on val, update OVERNIGHT_REPORT.md, commit results.
- Locked test runs once, only for the selected configuration: `python benchmark/run.py --split test --i-am-final-report ...`.

## Blockers
- None external. CPU-only (4 cores, 15 GB): full LoRA (1408 ex x 2 epochs) ~5-6 h on CPU; GPU recommended (finetune/README.md).
