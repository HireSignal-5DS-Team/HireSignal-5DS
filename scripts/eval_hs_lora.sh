#!/bin/bash
# Verify Dali's adapter Daibalooo/hiresignal-qwen3-4b-matcher-lora against the untuned baseline, same conditions:
# same Q4_K_M base GGUF + llama.cpp runtime, same prompt p1, greedy decoding, validator, RAG, 202 val requirements.
# Public repo: no token. If it is made private, set HF_TOKEN (read-only) as an environment secret. Never printed.
# Resumable, fail-fast, one model job at a time. Usage: setsid nohup scripts/eval_hs_lora.sh >> /home/user/eval_hs_lora.log 2>&1 &
set -euo pipefail
cd "$(dirname "$0")/.."
exec 9>/home/user/hs_queue.lock; flock -n 9 || { echo "another eval queue is running"; exit 1; }
REPO=${HS_LORA_REPO:-HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora}  # public; HF_TOKEN only needed if private
P=${PYTHON:-/home/user/venv/bin/python}
export HF_HOME=${HF_HOME:-/home/user/hf} HIRESIGNAL_RAG_DIR=${HIRESIGNAL_RAG_DIR:?set HIRESIGNAL_RAG_DIR}
R=benchmark/results; mkdir -p $R/logs/queue
# 1. download + pin the adapter revision (no training data, no token in outputs)
ADIR=$($P - "$REPO" <<'EOF'
import json, os, sys
from huggingface_hub import HfApi, snapshot_download
repo = sys.argv[1]; tok = os.environ.get("HF_TOKEN") or None; api = HfApi(token=tok)
info = api.model_info(repo)
d = snapshot_download(repo, revision=info.sha, token=tok,
                      allow_patterns=["adapter_config.json", "adapter_model.safetensors", "*.md", "*.json"])
json.dump({"repo": repo, "sha": info.sha, "private": info.private, "files": sorted(s.rfilename for s in info.siblings)},
          open(f"{d}/hs_provenance.json", "w"), indent=2)
print(d)
EOF
)
echo "adapter at $ADIR"; cat "$ADIR/hs_provenance.json"
SHA=$($P -c "import json;print(json.load(open('$ADIR/hs_provenance.json'))['sha'])")
mkdir -p $R/adapter && cp "$ADIR/adapter_config.json" $R/adapter/hs_lora_adapter_config.json && cp "$ADIR/hs_provenance.json" $R/adapter/hs_lora_provenance.json
# 2. serve base + adapter on :8081 (base server on :8080 stays for the baseline)
if ! curl -s -m 3 http://127.0.0.1:8081/v1/models >/dev/null; then
  setsid nohup scripts/serve_qwen4b_lora.sh "$ADIR" 8081 > /home/user/llama_lora_server.log 2>&1 < /dev/null 9>&- &  # 9>&-: the long-lived server must not keep the queue lock
  for i in $(seq 1 120); do curl -s -m 3 http://127.0.0.1:8081/v1/models >/dev/null && break; sleep 5; done
fi
curl -s -m 3 http://127.0.0.1:8081/v1/models >/dev/null || { echo "lora server failed"; tail -20 /home/user/llama_lora_server.log; exit 1; }
# 3. same val runs as the baseline (qwen3-4b-q4-{rag,none}-val), resumable
export HS_LLM_REVISION="unsloth/Qwen3-4B-Instruct-2507-GGUF@a06e946b:Q4_K_M + $REPO@$SHA (llama.cpp --lora_path)"
for kn in rag none; do
  id=qwen3-4b-q4+hslora-$kn-val
  [ -f $R/$id/metrics.json ] && continue
  $P -m benchmark.run --backend openai --model "Qwen/Qwen3-4B-Instruct-2507+lora" --base-url http://127.0.0.1:8081/v1 \
     --split val --knowledge $kn --run-id $id >> $R/logs/queue/$id.log 2>&1
done
# 4. Judge (fine-tuned, fp32) on the new runs, then the consolidated table
J1=/home/user/judge_runs/deberta-hs-v1/best
if [ -f $J1/config.json ]; then
  for id in qwen3-4b-q4+hslora-rag-val qwen3-4b-q4+hslora-none-val; do
    [ -f $R/judge/${id}__finetuned/metrics.json ] || $P -m benchmark.judge_eval --run $id --judge-dir $J1 --name finetuned >> $R/logs/queue/judge-hslora.log 2>&1
  done
else echo "fine-tuned judge checkpoint missing (container reset): retrain with python -m finetune.train_judge --out /home/user/judge_runs/deberta-hs-v1"; fi
$P -m benchmark.consolidate --split val > /dev/null
echo "done: compare qwen3-4b-q4+hslora-* with qwen3-4b-q4-* in $R/CONSOLIDATED_val.md"
