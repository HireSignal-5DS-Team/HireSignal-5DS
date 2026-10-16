#!/bin/bash
# End-to-end RAG comparison on the Matcher: no-RAG vs legacy BM25 vs rag.gated.v1, on the fine-tuned Matcher
# (Qwen3-4B Q4_K_M + LoRA HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora, :8081) and on the base model (:8080).
# Same 202 bench-v1 val requirements, prompt p1, temperature 0, 192 new tokens, k = 3, same server for every arm
# of one model. Paired McNemar + bootstrap CI: rag_opt/e2e_report.py (rag/significance.py).
#
# COMPUTE WINDOW 1 ONLY. Refuses to start until STATUS.md on the orchestrator branch says window 1 (or 2) is open.
# One model job per container: holds /home/user/hs_queue.lock (the existing convention). Resumable: rerun the same
# command; finished arms are skipped (metrics.json present), unfinished arms resume from predictions.jsonl.
#
#   setsid nohup rag_opt/e2e_compare.sh >> /home/user/s1_e2e.log 2>&1 < /dev/null &
#
# Environment (defaults in brackets):
#   MODELS ["lora base"]   ARMS ["none bm25 gated"] (+ gated-qdrant needs sentence-transformers + e5-small)
#   REPEAT_NONE [1]        also run the none arm a second time (none-repeat): run-to-run noise floor of the server
#   LORA_URL [http://127.0.0.1:8081/v1]  BASE_URL [http://127.0.0.1:8080/v1]
#   START_SERVERS [1]      start a missing server with the S2/eval scripts (scripts/serve_qwen4b_lora.sh, llama_cpp.server)
#   LORA_DIR               local PEFT adapter snapshot (needed only to start the LoRA server)
#   HS_WINDOW_OK [0]       set to 1 only if the orchestrator opened window 1 but the status check cannot be fetched
#   PYTHON [/home/user/venv/bin/python]  GGUF  (same Q4_K_M file as the evaluation line)
set -euo pipefail
cd "$(dirname "$0")/.."
P=${PYTHON:-/home/user/venv/bin/python}
MODELS=${MODELS:-"lora base"}; ARMS=${ARMS:-"none bm25 gated"}; REPEAT_NONE=${REPEAT_NONE:-1}
LORA_URL=${LORA_URL:-http://127.0.0.1:8081/v1}; BASE_URL=${BASE_URL:-http://127.0.0.1:8080/v1}
GGUF=${GGUF:-/home/user/hf/hub/models--unsloth--Qwen3-4B-Instruct-2507-GGUF/snapshots/a06e946bb6b655725eafa393f4a9745d460374c9/Qwen3-4B-Instruct-2507-Q4_K_M.gguf}
OUT=rag_opt/results/e2e; mkdir -p $OUT/logs
log() { echo "=== $(date -u +%FT%TZ) $*"; }

# 0. compute window gate
if [ "${HS_WINDOW_OK:-0}" != 1 ]; then
  git fetch -q origin claude/beautiful-galileo-o36bdv || { log "cannot fetch orchestrator status"; exit 2; }
  git show origin/claude/beautiful-galileo-o36bdv:docs/orchestration/STATUS.md | grep -Eq 'Compute window: ?\**[12]' \
    || { log "compute window 1 is not open (docs/orchestration/STATUS.md on the orchestrator branch); nothing started"; exit 2; }
fi
exec 9>/home/user/hs_queue.lock; flock -n 9 || { log "another model job holds /home/user/hs_queue.lock"; exit 1; }
export HIRESIGNAL_RAG_DIR=${HIRESIGNAL_RAG_DIR:-$PWD/rag} OMP_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false

up() { curl -s -m 3 "$1/models" > /dev/null; }
start_server() {  # $1 model, $2 url
  local port=${2##*:}; port=${port%%/*}
  if [ "$1" = lora ]; then
    [ -n "${LORA_DIR:-}" ] || { log "LoRA server down and LORA_DIR unset (see scripts/eval_hs_lora.sh for the pinned download)"; exit 1; }
    setsid nohup scripts/serve_qwen4b_lora.sh "$LORA_DIR" "$port" > /home/user/s1_lora_server.log 2>&1 < /dev/null &
  else
    setsid nohup $P -m llama_cpp.server --model "$GGUF" --model_alias Qwen/Qwen3-4B-Instruct-2507 --n_ctx 4096 \
      --n_threads 4 --host 127.0.0.1 --port "$port" > /home/user/s1_base_server.log 2>&1 < /dev/null &
  fi
  for _ in $(seq 1 120); do up "$2" && return 0; sleep 5; done
  log "server for $1 did not come up"; exit 1
}

for model in $MODELS; do
  case $model in
    lora) URL=$LORA_URL; NAME="Qwen/Qwen3-4B-Instruct-2507+lora"
          REV="unsloth/Qwen3-4B-Instruct-2507-GGUF@a06e946b:Q4_K_M + HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora (llama.cpp --lora_path)"
          PROVF=benchmark/results/adapter/hs_lora_provenance.json ;;
    base) URL=$BASE_URL; NAME="Qwen/Qwen3-4B-Instruct-2507"
          REV="unsloth/Qwen3-4B-Instruct-2507-GGUF@a06e946bb6b655725eafa393f4a9745d460374c9:Q4_K_M"; PROVF= ;;
    *) log "unknown model $model"; exit 1 ;;
  esac
  up "$URL" || { [ "${START_SERVERS:-1}" = 1 ] && start_server "$model" "$URL"; } || { log "$model server down at $URL"; exit 1; }
  up "$URL" || { log "$model server down at $URL"; exit 1; }
  export HS_LLM_REVISION="$REV"
  arms=$ARMS; [ "$REPEAT_NONE" = 1 ] && arms="$arms none-repeat"
  for arm in $arms; do
    id=${model}__${arm}; [ -f $OUT/$id/metrics.json ] && { log "skip $id (done)"; continue; }
    log "start $id"
    $P -m rag_opt.run_arm --arm "${arm%-repeat}" ${PROVF:+--adapter-provenance $PROVF} --backend openai --model "$NAME" \
       --base-url "$URL" --split val --k 3 --max-new-tokens 192 --run-id "$id" --out-root $OUT >> $OUT/logs/$id.log 2>&1 \
      || { log "FAILED $id (see $OUT/logs/$id.log); resume by rerunning this script"; exit 1; }
    log "done $id: $(tail -1 $OUT/logs/$id.log)"
  done
done
$P -m rag_opt.e2e_report --root $OUT
log "report: $OUT/e2e_report.md (commit $OUT with its predictions, config and provenance files)"
