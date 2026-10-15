#!/bin/bash
# Kus-hal/resume-screener-lora investigation (inference variants). Detached, resumable, idempotent.
# Waits for scripts/continue_benchmark.sh to finish (never runs two model jobs at once), then for each variant:
# runs (skips if metrics.json exists), applies the post-hoc adapters, commits and pushes.
# Launch: setsid nohup scripts/kushal_study.sh > /home/user/kushal_study.log 2>&1 < /dev/null &
cd "$(dirname "$0")/.." || exit 1
export HF_HOME=${HF_HOME:-/home/user/hf} HF_HUB_OFFLINE=1
export HIRESIGNAL_RAG_DIR=${HIRESIGNAL_RAG_DIR:-/tmp/claude-0/-home-user-HireSignal-5DS/97ee016c-75ae-56a3-81f8-f70ab21d59a7/scratchpad/ragsrc/rag}
P=${PYTHON:-/home/user/venv/bin/python}
while pgrep -f continue_benchmark.sh >/dev/null; do sleep 30; done
Q="--model Qwen/Qwen2.5-0.5B-Instruct --revision 7ae557604adf67be50417f59c2c2f167def9a775"
K="--adapter Kus-hal/resume-screener-lora --adapter-revision e4c042f538b4a899b9aa2f2d38bbc39d27fb7aa6"
push() {
  git add benchmark/results && git commit -q -m "results: Kus-hal study $1 (val) [automatic checkpoint]

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pC4cWnLapLopyiUgf8VmG" || true
  for i in 1 2 3 4; do git push -q origin claude/kind-albattani-k7qlt9 && break; sleep $((2 ** i)); done
}
run() {
  id=$1; shift
  if [ ! -f "benchmark/results/$id/metrics.json" ]; then
    echo "=== $(date -u +%H:%M:%S) start $id"
    $P -m benchmark.run --backend transformers --split val --knowledge rag --run-id "$id" "$@" 2>&1 | grep -E '^\{"run_id|Error|Traceback'
  fi
  [ -f "benchmark/results/$id/metrics.json" ] && $P -m benchmark.rescore --run "$id" --adapter schema_repair
  push "$id"
}
run kushal-native-prompt-rag-val $Q $K --prompt-variant kushal_native
[ -f benchmark/results/kushal-native-prompt-rag-val/metrics.json ] && $P -m benchmark.rescore --run kushal-native-prompt-rag-val --adapter kushal_native && push native-adapter
run kushal-constrained-rag-val $Q $K --constrained
run qwen2.5-constrained-rag-val $Q --constrained
run kushal-oneshot-rag-val $Q $K --prompt-variant p1_oneshot
run qwen2.5-oneshot-rag-val $Q --prompt-variant p1_oneshot
run qwen2.5-native-prompt-rag-val $Q --prompt-variant kushal_native
$P -m benchmark.consolidate --split val > /dev/null && push "consolidated table"
echo "=== $(date -u +%H:%M:%S) study done"
