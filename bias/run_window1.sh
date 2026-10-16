#!/bin/bash
# S4 Bias Auditor live measurement. RUN ONLY AFTER THE ORCHESTRATOR OPENS COMPUTE WINDOW 1 (docs/orchestration/STATUS.md).
# Uses the servers of the agent pipeline (docs/AGENT_PIPELINE.md); starts nothing itself:
#   :8081  Qwen3-4B-Instruct-2507 Q4_K_M + Matcher LoRA (scripts/serve_qwen4b_lora.sh <adapter-dir> 8081)
#   :8080  Qwen3-4B-Instruct-2507 Q4_K_M, no adapter (fallback Matcher; also serves the prompted Bias reviewer)
# One model job at a time per container: every step holds /home/user/hs_queue.lock.
#
#   HIRESIGNAL_RAG_DIR=<rag dir> bias/run_window1.sh [step ...]
#   steps: reviewer lora-new base-new (default, in order); lora-core lora-all base-all (optional)
#   lora-core is NOT in the default: the evaluation session runs that exact protocol (bias-qwen3-4b-q4+hslora, core
#   attributes, n=30, seed 0, BM25) on its own branch; lora-new/base-new complement it on the same requirements.
#
# Outputs (each with metrics.json + per-item jsonl + provenance) under benchmark/results/bias/:
#   review-qwen3-4b-q4-reviewer_v1     reviewer precision/recall on dev/test/holdout, latency, server RSS   (~110 calls)
#   bias-qwen3-4b-q4+hslora-new        LoRA Matcher, 5 new protected attributes + placebo, same 30 reqs   (360 calls)
#   bias-qwen3-4b-q4-new               base Matcher, same, paired with lora-new                           (360 calls)
#   bias-qwen3-4b-q4+hslora            (optional) LoRA Matcher, core attributes, paired with the base run   (240 calls)
#   bias-qwen3-4b-q4+hslora-all        LoRA Matcher, 9 protected attributes + placebo                     (600 calls)
#   bias-qwen3-4b-q4-all               base Matcher, same, paired with the LoRA run                       (600 calls)
set -euo pipefail
cd "$(dirname "$0")/.."
P=${PYTHON:-python}
LOCK=${HS_LOCK:-/home/user/hs_queue.lock}
LORA_URL=${HS_MATCHER_URL:-http://127.0.0.1:8081/v1}
BASE_URL=${HS_FALLBACK_URL:-http://127.0.0.1:8080/v1}
ADAPTER=HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora
ADAPTER_SHA=${ADAPTER_SHA:-0b6925b1e3c89b6b266b10bcd30af4c6a0c2dc3a}
export HS_LLM_REVISION=${HS_LLM_REVISION:-unsloth/Qwen3-4B-Instruct-2507-GGUF@a06e946bb6b655725eafa393f4a9745d460374c9:Q4_K_M}
N=${N:-30}
R=benchmark/results/bias

up() { curl -sf --max-time 5 "$1/models" >/dev/null || { echo "server $1 is not up; start it first (docs/AGENT_PIPELINE.md)"; exit 1; }; }
# the server's own python process (a wrapper shell's command line can contain the same text)
pid_of() { for p in $(pgrep -f "llama_cpp.server.*--port $1"); do readlink "/proc/$p/exe" | grep -q python && { echo "$p"; return; }; done; true; }
run() { flock "$LOCK" nice -n 5 "$@"; }

STEPS=${*:-reviewer lora-new base-new}
for s in $STEPS; do
  case $s in
    reviewer)
      up "$BASE_URL"; PID=$(pid_of 8080)
      run $P -m bias.review_eval --backend openai --base-url "$BASE_URL" --model Qwen/Qwen3-4B-Instruct-2507 \
        --splits dev,test,holdout --run-id review-qwen3-4b-q4-reviewer_v1 ${PID:+--server-pid $PID} ;;
    lora-core)
      up "$LORA_URL"; PID=$(pid_of 8081)
      run $P -m benchmark.bias_eval --backend openai --base-url "$LORA_URL" --model "Qwen/Qwen3-4B-Instruct-2507+lora" \
        --adapter-id "$ADAPTER" --adapter-revision "$ADAPTER_SHA" --attributes core --n "$N" \
        --run-id bias-qwen3-4b-q4+hslora --compare-to $R/bias-qwen3-4b-q4 ${PID:+--server-pid $PID} ;;
    lora-new)
      up "$LORA_URL"; PID=$(pid_of 8081)
      run $P -m benchmark.bias_eval --backend openai --base-url "$LORA_URL" --model "Qwen/Qwen3-4B-Instruct-2507+lora" \
        --adapter-id "$ADAPTER" --adapter-revision "$ADAPTER_SHA" --attributes new+placebo --n "$N" \
        --run-id bias-qwen3-4b-q4+hslora-new ${PID:+--server-pid $PID} ;;
    base-new)
      up "$BASE_URL"; PID=$(pid_of 8080)
      run $P -m benchmark.bias_eval --backend openai --base-url "$BASE_URL" --model Qwen/Qwen3-4B-Instruct-2507 \
        --attributes new+placebo --n "$N" --run-id bias-qwen3-4b-q4-new --compare-to $R/bias-qwen3-4b-q4+hslora-new \
        ${PID:+--server-pid $PID} ;;
    lora-all)
      up "$LORA_URL"; PID=$(pid_of 8081)
      run $P -m benchmark.bias_eval --backend openai --base-url "$LORA_URL" --model "Qwen/Qwen3-4B-Instruct-2507+lora" \
        --adapter-id "$ADAPTER" --adapter-revision "$ADAPTER_SHA" --attributes all --n "$N" \
        --run-id bias-qwen3-4b-q4+hslora-all ${PID:+--server-pid $PID} ;;
    base-all)
      up "$BASE_URL"; PID=$(pid_of 8080)
      run $P -m benchmark.bias_eval --backend openai --base-url "$BASE_URL" --model Qwen/Qwen3-4B-Instruct-2507 \
        --attributes all --n "$N" --run-id bias-qwen3-4b-q4-all --compare-to $R/bias-qwen3-4b-q4+hslora-all \
        ${PID:+--server-pid $PID} ;;
    *) echo "unknown step $s"; exit 2 ;;
  esac
done
echo "done. Commit the run directories above under $R/"
