#!/bin/bash
# Serve Qwen3-4B-Instruct-2507 + a PEFT LoRA adapter through llama.cpp (OpenAI-compatible), on the SAME
# Q4_K_M base GGUF as the untuned Matcher baseline, so a comparison changes only the adapter.
# Usage: scripts/serve_qwen4b_lora.sh <peft-adapter-dir> [port=8081]
#   1. checks adapter_config.json (PEFT LoRA, base must be Qwen/Qwen3-4B-Instruct-2507)
#   2. converts the adapter to GGUF with llama.cpp's convert_lora_to_gguf.py (vendored in llama-cpp-python 0.3.16)
#   3. starts the server with --lora_path (model alias Qwen/Qwen3-4B-Instruct-2507+lora)
set -euo pipefail
ADAPTER=${1:?adapter dir}; PORT=${2:-8081}
P=${PYTHON:-/home/user/venv/bin/python}
CONV=${LLAMA_CPP_SRC:-/home/user/llamacpp_src/llama_cpp_python-0.3.16/vendor/llama.cpp}/convert_lora_to_gguf.py
BASE_HF=${BASE_HF:-/home/user/hf/hub/models--Qwen--Qwen3-4B-Instruct-2507/snapshots/cdbee75f17c01a7cc42f958dc650907174af0554}
GGUF=${GGUF:-/home/user/hf/hub/models--unsloth--Qwen3-4B-Instruct-2507-GGUF/snapshots/a06e946bb6b655725eafa393f4a9745d460374c9/Qwen3-4B-Instruct-2507-Q4_K_M.gguf}
$P - "$ADAPTER" <<'EOF'
import json, sys
c = json.load(open(f"{sys.argv[1]}/adapter_config.json"))
assert c.get("peft_type") == "LORA", f"not a LoRA adapter: {c.get('peft_type')}"
base = (c.get("base_model_name_or_path") or "").replace("\\", "/").rstrip("/")
assert base.split("/")[-2:] == ["Qwen", "Qwen3-4B-Instruct-2507"] or base.endswith("Qwen3-4B-Instruct-2507"), f"adapter base is {base!r}"
print("adapter ok:", {k: c.get(k) for k in ("base_model_name_or_path", "revision", "r", "lora_alpha", "target_modules", "task_type")})
EOF
OUT=$ADAPTER/hiresignal-lora-f16.gguf
[ -f "$OUT" ] || $P "$CONV" "$ADAPTER" --base "$BASE_HF" --outtype f16 --outfile "$OUT"
exec $P -m llama_cpp.server --model "$GGUF" --lora_path "$OUT" --model_alias "Qwen/Qwen3-4B-Instruct-2507+lora" \
  --n_ctx 4096 --n_threads 4 --host 127.0.0.1 --port "$PORT"
