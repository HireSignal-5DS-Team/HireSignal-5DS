#!/bin/bash
# Restore the local llama.cpp servers after a container restart. Idempotent: it never stops or restarts a server.
#   8081  Qwen3-4B-Instruct-2507 Q4_K_M + HireSignal LoRA  (scripts/serve_qwen4b_lora.sh, cached adapter GGUF)
#   8080  the same base, no adapter                         (same command as ensure_server() in scripts/hs_queue.sh)
# For each port: GET /v1/models == 200 -> nothing to do; a server process for the port already exists -> wait for it;
# the port is held by another process -> log the conflict and skip it (nothing is killed); a model file is
# missing -> log it and skip (nothing is downloaded or converted). Otherwise the server is started and waited for.
# Started servers do not inherit this script's lock or any other descriptor (no queue lock is ever held).
# Run by a user-level SessionStart hook:  setsid nohup scripts/ensure_servers.sh >/dev/null 2>&1 </dev/null &
set -uo pipefail
cd "$(dirname "$0")/.."
LOG=${HS_ENSURE_LOG:-/home/user/ensure_servers.log}
exec >>"$LOG" 2>&1 </dev/null
for fd in $(ls /proc/$$/fd); do [ "$fd" -gt 2 ] && [ "$fd" -ne 255 ] && eval "exec $fd>&-"; done  # drop inherited descriptors (255 = bash reading this script)
log() { echo "$(date -u +%FT%TZ) [$$] $*"; }
exec 7>/home/user/hs_ensure.lock
flock -n 7 || { log "another ensure_servers.sh is running; exit"; exit 0; }

P=${PYTHON:-/home/user/venv/bin/python}
GGUF=/home/user/hf/hub/models--unsloth--Qwen3-4B-Instruct-2507-GGUF/snapshots/a06e946bb6b655725eafa393f4a9745d460374c9/Qwen3-4B-Instruct-2507-Q4_K_M.gguf
ADAPTER=/home/user/hf/hub/models--HireSignal-5DS-Team--hiresignal-qwen3-4b-matcher-lora/snapshots/0b6925b1e3c89b6b266b10bcd30af4c6a0c2dc3a

up() { [ "$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$1/v1/models")" = 200 ]; }
ours() {  # anchored on the executable, so a shell whose command line merely mentions the server is not matched
  pgrep -f -- "^[^ ]*python[0-9.]* -m llama_cpp\.server .*--port $1( |\$)|^[^ ]*bash [^ ]*serve_qwen4b_lora\.sh .* $1\$"; }
wait_up() { for _ in $(seq 1 60); do up "$1" && return 0; sleep 5; done; return 1; }

ensure() {  # ensure <port> <log file> <command...>
  local port=$1 slog=$2; shift 2
  if up "$port"; then log "$port: healthy (HTTP 200), nothing started"; return 0; fi
  local pids; pids=$(ours "$port" | tr '\n' ' ')
  if [ -n "$pids" ]; then
    log "$port: server process already present (pid $pids), waiting instead of starting"
    wait_up "$port" && { log "$port: healthy"; return 0; }
    log "$port: FAILED, existing process (pid $pids) not ready after 300s, see $slog"; return 1
  fi
  local holder; holder=$(lsof -nP -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ')
  if [ -n "$holder" ]; then log "$port: CONFLICT, port held by pid $holder (not a HireSignal server); skipped, nothing killed"; return 1; fi
  local f; for f in "$GGUF" "$ADAPTER/adapter_config.json" "$ADAPTER/hiresignal-lora-f16.gguf"; do
    [ -f "$f" ] || { log "$port: missing model file $f; not started (no download or conversion here)"; return 1; }
  done
  log "$port: starting: $*"
  (for fd in $(ls /proc/$BASHPID/fd); do [ "$fd" -gt 2 ] && [ "$fd" -ne 255 ] && eval "exec $fd>&-"; done
   exec setsid nohup "$@") >>"$slog" 2>&1 </dev/null &  # the server keeps no lock or other inherited descriptor
  wait_up "$port" && { log "$port: started, healthy (HTTP 200)"; return 0; }
  log "$port: FAILED to become ready within 300s, see $slog"; return 1
}

rc=0
ensure 8081 /home/user/llama_lora_server.log scripts/serve_qwen4b_lora.sh "$ADAPTER" 8081 || rc=1
ensure 8080 /home/user/llama_server.log "$P" -m llama_cpp.server --model "$GGUF" --model_alias Qwen/Qwen3-4B-Instruct-2507 \
  --n_ctx 4096 --n_threads 4 --host 127.0.0.1 --port 8080 || rc=1
log "done (rc=$rc)"
exit $rc
