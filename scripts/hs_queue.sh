#!/bin/bash
# HireSignal evaluation queue: ONE CPU-heavy job at a time, resumable, fail-fast. Replaces post_queue.sh.
# Order: qwen-rag -> qwen-norag -> bias -> judge-pretrained -> judge-finetune(+eval).
# - flock: a second copy exits immediately (no duplicate jobs).
# - A stage is skipped ONLY when its completion check passes (expected row counts, metrics present).
# - Unfinished stages resume from their own checkpoint (predictions/findings jsonl skip finished keys).
# - Any failure stops the queue (QUEUE_FAILED marker + log), nothing is skipped silently.
# - After each stage: results + logs committed and pushed (git under its own flock, safe with manual commits).
# - Model server (llama.cpp, OpenAI-compatible) is (re)started if missing; it is idle during Judge stages.
# Launch / resume (also after a container restart):
#   setsid nohup scripts/hs_queue.sh >> /home/user/hs_queue.log 2>&1 < /dev/null &
set -u
cd "$(dirname "$0")/.." || exit 1
exec 9>/home/user/hs_queue.lock
flock -n 9 || { echo "hs_queue already running"; exit 0; }
export HIRESIGNAL_RAG_DIR=${HIRESIGNAL_RAG_DIR:-/tmp/claude-0/-home-user-HireSignal-5DS/97ee016c-75ae-56a3-81f8-f70ab21d59a7/scratchpad/ragsrc/rag}
export HS_LLM_REVISION=${HS_LLM_REVISION:-"unsloth/Qwen3-4B-Instruct-2507-GGUF@a06e946bb6b655725eafa393f4a9745d460374c9:Q4_K_M"}
export OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false  # Judge stages: all 4 cores, server idle
P=${PYTHON:-/home/user/venv/bin/python}
R=benchmark/results
LOGS=$R/logs/queue
mkdir -p "$LOGS"
GGUF=/home/user/hf/hub/models--unsloth--Qwen3-4B-Instruct-2507-GGUF/snapshots/a06e946bb6b655725eafa393f4a9745d460374c9/Qwen3-4B-Instruct-2507-Q4_K_M.gguf
J0=/home/user/hf/hub/models--MoritzLaurer--DeBERTa-v3-base-mnli-fever-anli/snapshots/6f5cf0a2b59cabb106aca4c287eed12e357e90eb
J1=/home/user/judge_runs/deberta-hs-v1
JRUNS="lexical-rag-val qwen3-4b-q4-rag-val qwen3-4b-q4-none-val"
URL=http://127.0.0.1:8080/v1
log() { echo "=== $(date -u +%H:%M:%S) $*"; }
fail() { log "FAILED: $*"; echo "$(date -u) $*" > $R/QUEUE_FAILED; commit "queue FAILED at: $*"; exit 1; }

commit() {
  ( flock 8
    git add -A benchmark/results >/dev/null 2>&1
    git diff --cached --quiet || git commit -q -m "results: $1 [hs_queue.sh]

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pC4cWnLapLopyiUgf8VmG"
    for i in 1 2 3 4; do git push -q origin claude/kind-albattani-k7qlt9 2>/dev/null && break; sleep $((2 ** i)); done
  ) 8>/home/user/hs_git.lock
}

rows() { [ -f "$1" ] && wc -l < "$1" || echo 0; }
run_done() {  # benchmark run complete: metrics.json present and predictions cover all requirements of the split
  [ -f $R/$1/metrics.json ] && [ "$(rows $R/$1/predictions.jsonl)" -ge 202 ] && \
    $P -c "import json,sys; sys.exit(0 if json.load(open('$R/$1/metrics.json'))['n']==202 else 1)"
}
server_up() { curl -s -m 3 $URL/models >/dev/null; }
ensure_server() {
  server_up && return 0
  log "starting llama.cpp server"
  setsid nohup $P -m llama_cpp.server --model $GGUF --model_alias Qwen/Qwen3-4B-Instruct-2507 --n_ctx 4096 \
    --n_threads 4 --host 127.0.0.1 --port 8080 > /home/user/llama_server.log 2>&1 < /dev/null &
  for i in $(seq 1 120); do server_up && return 0; sleep 5; done
  fail "llama.cpp server did not start (see /home/user/llama_server.log)"
}
wait_legacy() {  # do not touch a run started by the older scripts: wait for it to exit, then verify
  while pgrep -f "scripts/run_qwen4b.sh|scripts/post_queue.sh" >/dev/null || pgrep -f "run-id $1( |$)" >/dev/null; do sleep 30; done
}

qwen_stage() {  # $1 knowledge rag|none
  id=qwen3-4b-q4-$1-val
  wait_legacy $id
  run_done $id && { log "skip $id (verified complete)"; return; }
  ensure_server
  log "run $id (resume from $(rows $R/$id/predictions.jsonl)/202)"
  $P -m benchmark.run --backend openai --model Qwen/Qwen3-4B-Instruct-2507 --base-url $URL --split val \
     --knowledge $1 --run-id $id >> $LOGS/$id.log 2>&1 || fail "$id (see $LOGS/$id.log)"
  run_done $id || fail "$id finished but completion check failed"
  commit "$id complete"
}

bias_stage() {
  id=bias-qwen3-4b-q4
  if [ -f $R/bias/$id/metrics.json ] && $P -c "import json,sys; sys.exit(0 if json.load(open('$R/bias/$id/metrics.json'))['n_requirements']==30 else 1)"; then
    log "skip $id (verified complete)"; return; fi
  ensure_server
  log "run $id (resume from $(rows $R/bias/$id/findings.jsonl)/30)"
  $P -m benchmark.bias_eval --backend openai --model Qwen/Qwen3-4B-Instruct-2507 --base-url $URL --n 30 \
     --run-id $id >> $LOGS/$id.log 2>&1 || fail "$id (see $LOGS/$id.log)"
  commit "$id complete"
}

judge_stage() {  # $1 name, $2 model dir
  for r in $JRUNS; do
    [ -f $R/judge/${r}__$1/metrics.json ] && { log "skip judge $1 on $r"; continue; }
    log "judge $1 on $r"
    $P -m benchmark.judge_eval --run $r --judge-dir $2 --name $1 >> $LOGS/judge-$1.log 2>&1 || fail "judge $1 on $r"
  done
  commit "judge $1 evals complete"
}

finetune_stage() {
  if [ ! -f $J1/train_meta.json ] || [ ! -f $J1/best/config.json ]; then
    log "judge fine-tuning"
    $P -m finetune.train_judge --out $J1 >> $LOGS/judge-finetune.log 2>&1 || fail "judge fine-tuning (see $LOGS/judge-finetune.log)"
  else log "skip judge fine-tuning (checkpoint present)"; fi
  cp $J1/train_meta.json $R/judge/finetuned_train_meta.json
  [ -f $R/judge/calibration_finetuned.json ] || $P -m benchmark.judge_eval --run lexical-rag-train --judge-dir $J1/best \
     --name finetuned --calibrate-only >> $LOGS/judge-finetuned.log 2>&1 || fail "judge finetuned calibration"
  judge_stage finetuned $J1/best
}

rm -f $R/QUEUE_FAILED
log "queue start (pid $$)"
qwen_stage rag
qwen_stage none
bias_stage
[ -f $R/judge/calibration_pretrained.json ] || $P -m benchmark.judge_eval --run lexical-rag-train --judge-dir $J0 \
   --name pretrained --calibrate-only >> $LOGS/judge-pretrained.log 2>&1 || fail "judge pretrained calibration"
judge_stage pretrained $J0
finetune_stage
$P -m benchmark.consolidate --split val > /dev/null 2>> $LOGS/consolidate.log || fail "consolidate"
commit "queue complete: consolidated table"
log "queue complete"
