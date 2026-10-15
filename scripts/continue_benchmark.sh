#!/bin/bash
# Detached continuation of the Matcher val benchmark (cloud container). Safe to re-run at any time:
# - waits for an already-running queue (pid given as $1) to exit, never touches it;
# - skips runs that already have metrics.json; unfinished runs resume from predictions.jsonl;
# - commits and pushes benchmark/results after every model.
# Launch:  setsid nohup scripts/continue_benchmark.sh <pid-of-running-queue-or-0> > benchmark/results/continue.log 2>&1 &
cd "$(dirname "$0")/.." || exit 1
WAIT_PID=${1:-0}
export HF_HOME=${HF_HOME:-/home/user/hf} HF_HUB_OFFLINE=1
export HIRESIGNAL_RAG_DIR=${HIRESIGNAL_RAG_DIR:-/tmp/claude-0/-home-user-HireSignal-5DS/97ee016c-75ae-56a3-81f8-f70ab21d59a7/scratchpad/ragsrc/rag}
P=${PYTHON:-/home/user/venv/bin/python}
SNAP=$HF_HOME/hub
FERMI=$SNAP/models--Zerflyne--FERMI-0.8B/snapshots/d21fa5400ff181083f5f8a07d82e6b8097f9cbc8
Q35=$SNAP/models--Qwen--Qwen3.5-0.8B/snapshots/2fc06364715b967f1860aea9cf38778875588b17

while [ "$WAIT_PID" != 0 ] && kill -0 "$WAIT_PID" 2>/dev/null; do sleep 30; done

push() {
  git add benchmark/results && git commit -q -m "results: $1 (val) [automatic checkpoint after model]

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015pC4cWnLapLopyiUgf8VmG" || true
  for i in 1 2 3 4; do git push -q origin claude/kind-albattani-k7qlt9 && break; sleep $((2 ** i)); done
}

run() {  # run-id, then benchmark.run arguments
  id=$1; shift
  if [ -f "benchmark/results/$id/metrics.json" ]; then echo "skip $id (done)"; return; fi
  echo "=== $(date -u +%H:%M:%S) start $id"
  $P -m benchmark.run --split val --knowledge rag --run-id "$id" "$@" 2>&1 | grep -E '^\{"run_id|Error|Traceback'
  push "$id"
}

# original queue (resumes if it was cut)
run qwen2.5-0.5b-rag-val --backend transformers --model Qwen/Qwen2.5-0.5B-Instruct --revision 7ae557604adf67be50417f59c2c2f167def9a775
run qwen2.5-0.5b+kushal-lora-rag-val --backend transformers --model Qwen/Qwen2.5-0.5B-Instruct --revision 7ae557604adf67be50417f59c2c2f167def9a775 \
    --adapter Kus-hal/resume-screener-lora --adapter-revision e4c042f538b4a899b9aa2f2d38bbc39d27fb7aa6
run qwen3-0.6b-rag-val --backend transformers --model Qwen/Qwen3-0.6B --revision c1899de289a04d12100db370d81485cdf75e47ca
run smollm2-360m-rag-val --backend transformers --model HuggingFaceTB/SmolLM2-360M-Instruct --revision a10cc1512eabd3dde888204e902eca88bddb4951
# extension (gw0/jobfit-model itself is not runnable: ONNX-only typed scorer; its base is benchmarked)
run smollm2-135m-rag-val --backend transformers --model HuggingFaceTB/SmolLM2-135M-Instruct --revision 12fd25f77366fa6b3b4b768ec3050bf629380bac
run flan-t5-small-rag-val --backend seq2seq --model google/flan-t5-small --revision 0fc9ddf78a1e988dac52e2dac162b0ede4fd74ab
run resume-scorer-t5-small-rag-val --backend seq2seq --model HumayunShahzad123/resume-scorer-t5-small --revision 209038761d88a42857749fd2cddcac4add3cdc81
run fermi-0.8b-rag-val --backend fermi --fermi-repo "$FERMI" --fermi-base "$Q35"
run qwen3.5-0.8b-rag-val --backend transformers --model Qwen/Qwen3.5-0.8B --revision 2fc06364715b967f1860aea9cf38778875588b17
$P -m benchmark.consolidate --split val > /dev/null && push "consolidated table"
echo "=== $(date -u +%H:%M:%S) all done"
