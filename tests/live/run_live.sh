#!/usr/bin/env bash
# One LIVE QA job (window 1+): takes the shared model queue lock, serves the LoRA Matcher (:8081) and the base
# fallback (:8080) from the pinned Q4_K_M GGUF with llama.cpp, runs tests/live with provenance, stops the servers.
#   tests/live/run_live.sh [out-dir]        (default docs/qa/live_runs/<UTC timestamp>)
# Env: PYTHON (venv with llama-cpp-python 0.3.16 [server]), ADAPTER_DIR (PEFT adapter snapshot), GGUF, HS_RAG
# (default none: the QA probes test the Matcher contracts; set bm25 + HIRESIGNAL_RAG_DIR to include retrieval).
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT=${1:-docs/qa/live_runs/$(date -u +%Y%m%dT%H%M%SZ)}
P=${PYTHON:-/home/user/venv/bin/python}
H=${HF_HOME:-/home/user/hf}
ADAPTER_DIR=${ADAPTER_DIR:-$H/hub/models--HireSignal-5DS-Team--hiresignal-qwen3-4b-matcher-lora/snapshots/0b6925b1e3c89b6b266b10bcd30af4c6a0c2dc3a}
GGUF=${GGUF:-$H/hub/models--unsloth--Qwen3-4B-Instruct-2507-GGUF/snapshots/a06e946bb6b655725eafa393f4a9745d460374c9/Qwen3-4B-Instruct-2507-Q4_K_M.gguf}
export BASE_HF=${BASE_HF:-$H/hub/models--Qwen--Qwen3-4B-Instruct-2507/snapshots/cdbee75f17c01a7cc42f958dc650907174af0554}
export GGUF PYTHON=$P
exec 9>/home/user/hs_queue.lock
flock -n 9 || { echo "another model job holds /home/user/hs_queue.lock"; exit 1; }
mkdir -p "$OUT"
pids=()
cleanup() { for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT
up() { curl -s -m 3 "http://127.0.0.1:$1/v1/models" >/dev/null; }
if ! up 8081; then
  setsid scripts/serve_qwen4b_lora.sh "$ADAPTER_DIR" 8081 9>&- > "$OUT/server_lora.log" 2>&1 < /dev/null & pids+=($!)
fi
if ! up 8080; then
  setsid "$P" -m llama_cpp.server --model "$GGUF" --model_alias Qwen/Qwen3-4B-Instruct-2507 --n_ctx 4096 --n_threads 4 \
    --host 127.0.0.1 --port 8080 9>&- > "$OUT/server_base.log" 2>&1 < /dev/null & pids+=($!)
fi
for i in $(seq 1 180); do up 8081 && up 8080 && break; sleep 5; done
up 8081 || { echo "LoRA server did not start"; tail -20 "$OUT/server_lora.log"; exit 1; }
SHA=$(basename "$ADAPTER_DIR")
export HS_LIVE=1 HS_LIVE_OUT="$OUT" HS_RAG=${HS_RAG:-none} HS_TIMEOUT=${HS_TIMEOUT:-300} \
  HS_MATCHER_URL=http://127.0.0.1:8081/v1 HS_FALLBACK_URL=http://127.0.0.1:8080/v1 \
  HS_LLM_REVISION="unsloth/Qwen3-4B-Instruct-2507-GGUF@a06e946b:Q4_K_M + HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@$SHA (llama.cpp --lora_path)"
set +e
python -m pytest tests/live -v -rxXs -p no:cacheprovider 2>&1 | tee "$OUT/pytest.txt"
rc=${PIPESTATUS[0]}
echo "LIVE run dir: $OUT (rc=$rc)"
exit $rc
