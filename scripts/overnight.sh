#!/usr/bin/env bash
# Resumable overnight pipeline (CPU). Every stage skips work already done, so re-running continues.
# Usage: nohup bash scripts/overnight.sh > logs/overnight.log 2>&1 &
set -u
cd "$(dirname "$0")/.."
export OMP_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false
mark() { echo "[$(date -u +%FT%TZ)] $*"; }
val() {  # val <out_name> <args...>
  local out=benchmark/results/$1; shift
  [ -f "$out/metrics.json" ] && [ "$(python -c "import json;print(json.load(open('$out/metrics.json'))['metrics']['n'])" 2>/dev/null)" = 110 ] && { mark "skip $out"; return; }
  mark "start $out"; python benchmark/run.py --split val --backend transformers --out "$out" "$@" || mark "FAILED $out"
}
# Stage 1: zero-shot base arms with RAG (best smoke first)
for a in qwen3.5-0.8b qwen2.5-0.5b qwen3-0.6b lfm2.5-350m; do val "val_${a}_rag" --arm "$a" --knowledge rag; done
# Stage 2: LoRA pilot on Qwen2.5-0.5B (train split only; resumes from latest checkpoint)
[ -d finetune/runs/qwen25_05b_lora_pilot/final ] || { mark "start lora pilot"; python -m finetune.train_lora --config finetune/configs/qwen25_05b_pilot.yaml || mark "FAILED lora pilot"; }
[ -d finetune/runs/qwen25_05b_lora_pilot/best ] && val val_qwen2.5-0.5b+pilot-lora_rag --arm qwen2.5-0.5b --adapter finetune/runs/qwen25_05b_lora_pilot/best --knowledge rag
# Stage 3: remaining arms (existing adapter = negative control) and RAG ablation
for a in qwen2.5-0.5b+kushal-lora smollm2-360m granite-4.0-350m lfm2-350m; do val "val_${a}_rag" --arm "$a" --knowledge rag; done
val val_qwen3.5-0.8b_none --arm qwen3.5-0.8b --knowledge none
python benchmark/compare.py
mark "done"
