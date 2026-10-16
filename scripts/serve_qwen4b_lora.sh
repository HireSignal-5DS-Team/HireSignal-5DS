#!/bin/bash
# Serve Qwen3-4B-Instruct-2507 + a PEFT LoRA adapter through llama.cpp (OpenAI-compatible), on the SAME
# Q4_K_M base GGUF as the untuned Matcher baseline, so a comparison changes only the adapter.
# Usage: scripts/serve_qwen4b_lora.sh <peft-adapter-dir> [port=8081]
#   1. checks adapter_config.json (PEFT LoRA, base must be Qwen/Qwen3-4B-Instruct-2507) and, when the adapter dir has
#      hs_provenance.json (scripts/check_matcher_lora.py --download, scripts/eval_hs_lora.sh), that its sha is the one
#      pinned in config/matcher_models.json (HS_ALLOW_UNPINNED=1 to serve another revision on purpose)
#   2. converts the adapter to GGUF with llama.cpp's convert_lora_to_gguf.py (vendored in llama-cpp-python 0.3.16);
#      the converter needs only the base config.json (BASE_HF), never the base weights
#   3. starts the server with --lora_path (model alias Qwen/Qwen3-4B-Instruct-2507+lora)
# Fresh container: python scripts/check_matcher_lora.py --download fetches everything under $HS_MODELS_DIR.
set -euo pipefail
ADAPTER=$(realpath "${1:?adapter dir}"); PORT=${2:-8081}
cd "$(dirname "$0")/.."
P=${PYTHON:-/home/user/venv/bin/python}
M=${HS_MODELS_DIR:-/home/user/hs_models}
CONV=${LLAMA_CPP_SRC:-/home/user/llamacpp_src/llama_cpp_python-0.3.16/vendor/llama.cpp}/convert_lora_to_gguf.py
BASE_HF=${BASE_HF:-/home/user/hf/hub/models--Qwen--Qwen3-4B-Instruct-2507/snapshots/cdbee75f17c01a7cc42f958dc650907174af0554}
[ -f "$BASE_HF/config.json" ] || BASE_HF=$M/base_config
GGUF=${GGUF:-/home/user/hf/hub/models--unsloth--Qwen3-4B-Instruct-2507-GGUF/snapshots/a06e946bb6b655725eafa393f4a9745d460374c9/Qwen3-4B-Instruct-2507-Q4_K_M.gguf}
[ -f "$GGUF" ] || GGUF=$M/gguf/Qwen3-4B-Instruct-2507-Q4_K_M.gguf
$P - "$ADAPTER" <<'EOF'
import json, os, sys
c = json.load(open(f"{sys.argv[1]}/adapter_config.json"))
assert c.get("peft_type") == "LORA", f"not a LoRA adapter: {c.get('peft_type')}"
base = (c.get("base_model_name_or_path") or "").replace("\\", "/").rstrip("/")
assert base.split("/")[-2:] == ["Qwen", "Qwen3-4B-Instruct-2507"] or base.endswith("Qwen3-4B-Instruct-2507"), f"adapter base is {base!r}"
pin = json.load(open("config/matcher_models.json"))["primary"]["adapter"]
prov = f"{sys.argv[1]}/hs_provenance.json"
if os.path.exists(prov):
    got = json.load(open(prov))
    if (got.get("repo"), got.get("sha")) != (pin["repo"], pin["sha"]) and os.environ.get("HS_ALLOW_UNPINNED") != "1":
        sys.exit(f"adapter {got.get('repo')}@{got.get('sha')} is not the pinned {pin['repo']}@{pin['sha']}")
    print("adapter revision:", got.get("repo"), got.get("sha"))
else:
    print("WARNING: no hs_provenance.json in the adapter dir; revision unverified (pinned:", pin["sha"], ")")
print("adapter ok:", {k: c.get(k) for k in ("base_model_name_or_path", "revision", "r", "lora_alpha", "target_modules", "task_type")})
EOF
[ -f "$CONV" ] || { echo "convert_lora_to_gguf.py not found at $CONV (set LLAMA_CPP_SRC)"; exit 1; }
[ -f "$BASE_HF/config.json" ] || { echo "base config.json not found (set BASE_HF)"; exit 1; }
[ -f "$GGUF" ] || { echo "base GGUF not found (set GGUF)"; exit 1; }
OUT=$ADAPTER/hiresignal-lora-f16.gguf
[ -f "$OUT" ] || $P "$CONV" "$ADAPTER" --base "$BASE_HF" --outtype f16 --outfile "$OUT"
exec $P -m llama_cpp.server --model "$GGUF" --lora_path "$OUT" --model_alias "Qwen/Qwen3-4B-Instruct-2507+lora" \
  --n_ctx 4096 --n_threads "${HS_THREADS:-4}" --host 127.0.0.1 --port "$PORT"
