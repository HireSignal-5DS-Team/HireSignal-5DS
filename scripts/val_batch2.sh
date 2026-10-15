#!/usr/bin/env bash
# Second val batch (each run resumable). Pilot adapter = finetune/runs/qwen25_05b_lora_pilot/best.
cd "$(dirname "$0")/.."
export OMP_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false
A=finetune/runs/qwen25_05b_lora_pilot/best
r() { echo "[$(date -u +%FT%TZ)] start $1"; out=benchmark/results/$1; shift; python benchmark/run.py --split val --backend transformers --out "$out" "$@" 2>&1 | grep -E "acc=|Error|error" ; }
r "val_qwen2.5-0.5b+pilot-lora_none" --arm qwen2.5-0.5b --adapter $A --knowledge none
r "val_qwen2.5-0.5b+kushal-lora_rag" --arm qwen2.5-0.5b+kushal-lora --knowledge rag
for a in smollm2-360m granite-4.0-350m lfm2-350m; do r "val_${a}_rag" --arm $a --knowledge rag; done
python benchmark/compare.py; echo "[$(date -u +%FT%TZ)] done"
