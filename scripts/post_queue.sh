#!/bin/bash
# Sequential evaluation queue (one CPU-heavy job at a time). Waits for scripts/run_qwen4b.sh, then:
#  1. Bias Auditor counterfactual run with Qwen3-4B (30 val requirements x 4 attributes x 2 variants)
#  2. Pretrained NLI Judge on lexical, Qwen RAG and Qwen no-RAG val predictions (tau calibrated on train-dev)
#  3. Judge fine-tuning on train (checkpoint outside git), calibration on train-dev, evaluation on the same runs
# Each step is resumable or cheap to repeat; results are committed and pushed after each step.
cd "$(dirname "$0")/.." || exit 1
export HIRESIGNAL_RAG_DIR=${HIRESIGNAL_RAG_DIR:-/tmp/claude-0/-home-user-HireSignal-5DS/97ee016c-75ae-56a3-81f8-f70ab21d59a7/scratchpad/ragsrc/rag}
export HS_LLM_REVISION=${HS_LLM_REVISION:-"unsloth/Qwen3-4B-Instruct-2507-GGUF@a06e946bb6b655725eafa393f4a9745d460374c9:Q4_K_M"}
P=${PYTHON:-/home/user/venv/bin/python}
J0=/home/user/hf/hub/models--MoritzLaurer--DeBERTa-v3-base-mnli-fever-anli/snapshots/6f5cf0a2b59cabb106aca4c287eed12e357e90eb
J1=/home/user/judge_runs/deberta-hs-v1
RUNS="lexical-rag-val qwen3-4b-q4-rag-val qwen3-4b-q4-none-val"
while pgrep -f "scripts/run_qwen4b.sh" >/dev/null; do sleep 30; done
push() {
  for i in 1 2 3; do
    git add benchmark/results && git commit -q -m "results: $1 [automatic, post_queue.sh]

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pC4cWnLapLopyiUgf8VmG" && break || sleep 5
  done
  for i in 1 2 3 4; do git push -q origin claude/kind-albattani-k7qlt9 2>/dev/null && break; sleep $((2 ** i)); done
}
step() { echo "=== $(date -u +%H:%M:%S) $*"; }
step "bias audit qwen3-4b"
$P -m benchmark.bias_eval --backend openai --model Qwen/Qwen3-4B-Instruct-2507 --base-url http://127.0.0.1:8080/v1 \
   --n 30 --run-id bias-qwen3-4b-q4 2>&1 | grep -E '^\{|Error|Trace'
push "bias audit qwen3-4b-q4"
step "pretrained judge evals"
for r in $RUNS; do $P -m benchmark.judge_eval --run $r --judge-dir $J0 --name pretrained 2>&1 | grep -E '^\{|Error|Trace'; done
push "pretrained judge evals"
step "judge fine-tuning"
[ -f $J1/train_meta.json ] || $P -m finetune.train_judge --out $J1 2>&1 | grep -E '^\{|Error|Trace'
mkdir -p benchmark/results/judge && cp $J1/train_meta.json benchmark/results/judge/finetuned_train_meta.json
$P -m benchmark.judge_eval --run lexical-rag-train --judge-dir $J1/best --name finetuned --calibrate-only 2>&1 | grep -E '^\{|Error|Trace'
for r in $RUNS; do $P -m benchmark.judge_eval --run $r --judge-dir $J1/best --name finetuned 2>&1 | grep -E '^\{|Error|Trace'; done
push "fine-tuned judge evals"
step "post_queue done"
