#!/bin/bash
# sequential experiment queue: one model job at a time; each run is resumable
cd /home/user/HireSignal-5DS
export HIRESIGNAL_RAG_DIR=/tmp/claude-0/-home-user-HireSignal-5DS/97ee016c-75ae-56a3-81f8-f70ab21d59a7/scratchpad/ragsrc/rag HF_HOME=/home/user/hf HF_HUB_OFFLINE=1
P=/home/user/venv/bin/python
run() { echo "=== $(date -u +%H:%M:%S) start $*"; $P -m benchmark.run --split val --knowledge rag "$@" 2>&1 | grep -E '^\{"run_id' ; }
run --backend transformers --model Qwen/Qwen2.5-0.5B-Instruct --revision 7ae557604adf67be50417f59c2c2f167def9a775 --run-id qwen2.5-0.5b-rag-val
run --backend transformers --model Qwen/Qwen2.5-0.5B-Instruct --revision 7ae557604adf67be50417f59c2c2f167def9a775 --adapter Kus-hal/resume-screener-lora --adapter-revision e4c042f538b4a899b9aa2f2d38bbc39d27fb7aa6 --run-id qwen2.5-0.5b+kushal-lora-rag-val
run --backend transformers --model Qwen/Qwen3-0.6B --revision c1899de289a04d12100db370d81485cdf75e47ca --run-id qwen3-0.6b-rag-val
run --backend transformers --model HuggingFaceTB/SmolLM2-360M-Instruct --revision a10cc1512eabd3dde888204e902eca88bddb4951 --run-id smollm2-360m-rag-val
echo "=== $(date -u +%H:%M:%S) queue done"
