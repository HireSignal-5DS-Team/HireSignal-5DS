#!/bin/bash
# One-command LIVE smoke test of the fine-tuned Matcher (compute window 1 only):
#   verify + fetch the pinned models -> start base (:8080) and LoRA (:8081) llama.cpp servers -> live pytest ->
#   3 val cases through the full pipeline (provenance, schema, citations, review, forced fallback) -> stop the servers.
# Usage: HS_COMPUTE_WINDOW=1 HIRESIGNAL_RAG_DIR=<rag dir> scripts/live_smoke.sh [cases=val-000,val-001,val-002]
# Needs: llama-cpp-python 0.3.16 (server extra), its vendored llama.cpp source (LLAMA_CPP_SRC, for the LoRA converter),
#        torch + safetensors + gguf (converter), huggingface_hub, jinja2, the team RAG code (HIRESIGNAL_RAG_DIR).
# Artefacts: benchmark/results/live_smoke/<UTC timestamp>/ (smoke.json, predictions.jsonl, reports, server logs).
set -euo pipefail
cd "$(dirname "$0")/.."
[ "${HS_COMPUTE_WINDOW:-0}" -ge 1 ] || { echo "refusing: compute window 1 not declared (HS_COMPUTE_WINDOW=1); see docs/orchestration/STATUS.md"; exit 2; }
: "${HIRESIGNAL_RAG_DIR:?set HIRESIGNAL_RAG_DIR (RAG stays enabled; HS_RAG=bm25 by default)}"
CASES=${1:-val-000,val-001,val-002}
P=${PYTHON:-/home/user/venv/bin/python}
export HS_MODELS_DIR=${HS_MODELS_DIR:-/home/user/hs_models} HS_RAG=${HS_RAG:-bm25}
CONV=${LLAMA_CPP_SRC:-/home/user/llamacpp_src/llama_cpp_python-0.3.16/vendor/llama.cpp}/convert_lora_to_gguf.py
[ -f "$CONV" ] || { echo "preflight: $CONV missing (set LLAMA_CPP_SRC)"; exit 1; }
$P -c "import llama_cpp, torch, safetensors, gguf, mistral_common, huggingface_hub, jinja2" \
  || { echo "preflight: install llama-cpp-python[server]==0.3.16, torch, safetensors, gguf, mistral_common, huggingface_hub, jinja2"; exit 1; }
RUN=benchmark/results/live_smoke/$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$RUN"
exec 9>/home/user/hs_queue.lock; flock -n 9 || { echo "another model job holds /home/user/hs_queue.lock"; exit 1; }
for port in 8080 8081; do
  if curl -s -m 3 "http://127.0.0.1:$port/v1/models" >/dev/null; then
    echo "port $port already serves a model; stop it first (this script only stops servers it started)"; exit 1
  fi
done
# 1. verify compatibility and fetch the pinned adapter, base config and Q4_K_M GGUF
$P scripts/check_matcher_lora.py --download --workdir "$HS_MODELS_DIR" --out "$RUN/lora_compat.json" | tee "$RUN/fetch.json"
GGUF=$HS_MODELS_DIR/gguf/Qwen3-4B-Instruct-2507-Q4_K_M.gguf
# 2. servers (same Q4_K_M weights, same runtime; only the adapter differs)
PIDS=()
stop() { for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done; wait 2>/dev/null || true; echo "servers stopped"; }
trap stop EXIT
setsid $P -m llama_cpp.server --model "$GGUF" --model_alias Qwen/Qwen3-4B-Instruct-2507 --n_ctx 4096 \
  --n_threads "${HS_THREADS:-4}" --host 127.0.0.1 --port 8080 > "$RUN/server-base.log" 2>&1 < /dev/null & PIDS+=($!)
BASE_HF=$HS_MODELS_DIR/base_config GGUF=$GGUF setsid scripts/serve_qwen4b_lora.sh "$HS_MODELS_DIR/adapter" 8081 \
  > "$RUN/server-lora.log" 2>&1 < /dev/null & PIDS+=($!)
for port in 8080 8081; do
  for i in $(seq 1 120); do curl -s -m 3 "http://127.0.0.1:$port/v1/models" >/dev/null && break; sleep 5; done
  curl -s -m 3 "http://127.0.0.1:$port/v1/models" | tee "$RUN/models-$port.json" || { echo "server :$port failed"; tail -30 "$RUN"/server-*.log; exit 1; }
  echo
done
# 3. live tests + smoke run (judge off by default; HS_SMOKE_JUDGE=1 adds it)
set +e
HS_LIVE=1 HS_LIVE_CASES=$CASES $P -m pytest -q -rs matcher/tests/test_live_matcher.py 2>&1 | tee "$RUN/pytest-live.txt"
T=${PIPESTATUS[0]}
HS_SMOKE_SERVERS=started $P scripts/live_smoke.py --out "$RUN" --cases "$CASES" ${HS_SMOKE_JUDGE:+--judge}
S=$?
set -e
echo "live pytest exit=$T, smoke exit=$S, artefacts in $RUN"
[ "$T" -eq 0 ] && [ "$S" -eq 0 ]
