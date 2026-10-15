#!/bin/bash
# Qwen3-4B-Instruct-2507 (GGUF Q4_K_M via local llama.cpp OpenAI-compatible server) Matcher runs. Resumable.
# Needs the server: python -m llama_cpp.server --model <gguf> --model_alias Qwen/Qwen3-4B-Instruct-2507 --n_ctx 4096 --port 8080
# Usage: scripts/run_qwen4b.sh <run-suffix> [benchmark.run args...]   e.g. scripts/run_qwen4b.sh q4 --split val
cd "$(dirname "$0")/.." || exit 1
export HIRESIGNAL_RAG_DIR=${HIRESIGNAL_RAG_DIR:-/tmp/claude-0/-home-user-HireSignal-5DS/97ee016c-75ae-56a3-81f8-f70ab21d59a7/scratchpad/ragsrc/rag}
export HS_LLM_REVISION=${HS_LLM_REVISION:-"unsloth/Qwen3-4B-Instruct-2507-GGUF@a06e946bb6b655725eafa393f4a9745d460374c9:Q4_K_M"}
P=${PYTHON:-/home/user/venv/bin/python}
for kn in rag none; do
  id=qwen3-4b-$1-$kn-val
  [ -f benchmark/results/$id/metrics.json ] && { echo "skip $id"; continue; }
  echo "=== $(date -u +%H:%M:%S) start $id"
  $P -m benchmark.run --backend openai --model Qwen/Qwen3-4B-Instruct-2507 --base-url http://127.0.0.1:8080/v1 \
     --split val --knowledge $kn --run-id $id 2>&1 | grep -E '^\{"run_id|Error|Traceback'
done
echo "=== $(date -u +%H:%M:%S) qwen4b done"
