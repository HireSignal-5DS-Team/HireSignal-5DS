#!/bin/bash
# Final real-model end-to-end run on the LOCKED bench-v1 test split (docs/orchestration/FINAL_RUN_PLAN.md).
# Orchestrator only. Resumable: rerun the same command; finished arms are skipped, unfinished arms resume.
#   setsid nohup scripts/final_run.sh >> /home/user/final_run.log 2>&1 < /dev/null &
# Env: PYTHON [/home/user/venv-orch/bin/python]  HS_MODELS_DIR [/home/user/hs_models]  ARMS ["lora:gated lora:none base:gated"]
set -euo pipefail
cd "$(dirname "$0")/.."
P=${PYTHON:-/home/user/venv-orch/bin/python}
M=${HS_MODELS_DIR:-/home/user/hs_models}; GGUF=$M/gguf/Qwen3-4B-Instruct-2507-Q4_K_M.gguf
ARMS=${ARMS:-"lora:gated lora:none base:gated"}
OUT=benchmark/results/final; mkdir -p $OUT/logs
log() { echo "=== $(date -u +%FT%TZ) $*"; }
up() { curl -s -m 3 "http://127.0.0.1:$1/v1/models" > /dev/null; }
exec 9>/home/user/hs_queue.lock; flock -n 9 || { log "another model job holds /home/user/hs_queue.lock"; exit 1; }
export HIRESIGNAL_RAG_DIR=${HIRESIGNAL_RAG_DIR:-$PWD/rag} OMP_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false HS_S6_TEST_UNLOCK=1
export LLAMA_CPP_SRC=${LLAMA_CPP_SRC:-/home/user/llamacpp_src/llama_cpp_python-0.3.16/vendor/llama.cpp}

PIDS=()
trap 'for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done; log "servers stopped"' EXIT
up 8080 || { setsid $P -m llama_cpp.server --model "$GGUF" --model_alias Qwen/Qwen3-4B-Instruct-2507 --n_ctx 4096 \
  --n_threads 4 --host 127.0.0.1 --port 8080 > $OUT/logs/server-base.log 2>&1 < /dev/null & PIDS+=($!); }
up 8081 || { PYTHON=$P BASE_HF=$M/base_config GGUF=$GGUF setsid scripts/serve_qwen4b_lora.sh "$M/adapter" 8081 \
  > $OUT/logs/server-lora.log 2>&1 < /dev/null & PIDS+=($!); }
for port in 8080 8081; do
  for _ in $(seq 1 120); do up $port && break; sleep 5; done
  up $port || { log "server :$port failed"; tail -30 $OUT/logs/server-*.log; exit 1; }
  curl -s "http://127.0.0.1:$port/v1/models" > $OUT/models-$port.json
done

for a in $ARMS; do
  model=${a%%:*}; arm=${a##*:}; id=${model}__${arm}
  [ -f $OUT/$id/metrics.json ] && { log "skip $id (done)"; continue; }
  if [ $model = lora ]; then URL=http://127.0.0.1:8081/v1; NAME="Qwen/Qwen3-4B-Instruct-2507+lora"
    export HS_LLM_REVISION="unsloth/Qwen3-4B-Instruct-2507-GGUF@a06e946b:Q4_K_M + HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1 (llama.cpp --lora_path)"
    PROV="--adapter-provenance benchmark/results/adapter/hs_lora_provenance.json"
  else URL=http://127.0.0.1:8080/v1; NAME="Qwen/Qwen3-4B-Instruct-2507"; PROV=
    export HS_LLM_REVISION="unsloth/Qwen3-4B-Instruct-2507-GGUF@a06e946bb6b655725eafa393f4a9745d460374c9:Q4_K_M"
  fi
  log "start $id"
  $P -m rag_opt.run_arm --arm "$arm" $PROV --backend openai --model "$NAME" --base-url "$URL" --split test \
     --i-understand-test-is-locked --k 3 --max-new-tokens 192 --run-id "$id" --out-root $OUT >> $OUT/logs/$id.log 2>&1 \
    || { log "FAILED $id (see $OUT/logs/$id.log); rerun to resume"; exit 1; }
  log "done $id"
done
$P -m rag_opt.e2e_report --root $OUT || log "e2e_report failed (arms are saved)"

# full production pipeline on 3 test cases (factory defaults; pretrained Judge)
for c in test-000 test-001 test-002; do
  [ -f $OUT/pipeline/$c/report.json ] || [ -d $OUT/pipeline/$c ] && continue
  $P scripts/run_pipeline.py --case $c --out $OUT/pipeline/$c >> $OUT/logs/pipeline.log 2>&1 || log "pipeline $c FAILED"
done
log "final run complete: $OUT"
