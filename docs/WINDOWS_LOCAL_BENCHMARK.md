# Running the Matcher benchmark on the Windows laptop (RTX 4050, 6 GB)

Use this procedure when the cloud environment cannot reach huggingface.co, or to get GPU latency numbers.
It runs exactly the same code, data, prompt and greedy decoding as the cloud runs. Only the hardware differs,
and `config.json` records it.

## 1. Environment (PowerShell, repo root)

```powershell
git fetch origin
git checkout claude/kind-albattani-k7qlt9
py -3.13 -m venv .venv ; .\.venv\Scripts\Activate.ps1
# CUDA build of torch first (CUDA 12.x wheels work with recent NVIDIA drivers), then the pinned rest
pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements-matcher.txt     # 2.14.1+cu128 already satisfies the torch pin, so it is kept
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

If that CUDA index has no 2.14.1 wheel (not checked from the cloud, download.pytorch.org was unreachable),
install the nearest available CUDA torch and change the `torch==` line in `requirements-matcher.txt` to match.
`config.json` of every run records the torch and transformers versions actually used.

## 2. RAG code without merging the RAG branch

The Matcher reads the team RAG (`rag/retrieval.py`, ESCO data) from `HIRESIGNAL_RAG_DIR`. Check the RAG branch
out next to the repo as a separate worktree. This is read-only and does not merge anything:

```powershell
git worktree add ..\HireSignal-rag origin/claude/gracious-fermi-ncuem4
$env:HIRESIGNAL_RAG_DIR = (Resolve-Path ..\HireSignal-rag\rag).Path
```

## 3. Model cache (pinned revisions)

```powershell
$env:HF_HOME = "D:\hf"   # any disk with ~4 GB free
python -c "from huggingface_hub import snapshot_download as d; [d(m, revision=r) for m, r in [('Qwen/Qwen2.5-0.5B-Instruct','7ae557604adf67be50417f59c2c2f167def9a775'),('Kus-hal/resume-screener-lora','e4c042f538b4a899b9aa2f2d38bbc39d27fb7aa6'),('Qwen/Qwen3-0.6B','c1899de289a04d12100db370d81485cdf75e47ca'),('HuggingFaceTB/SmolLM2-360M-Instruct','a10cc1512eabd3dde888204e902eca88bddb4951')]]"
```

## 4. Tests, then the queue

```powershell
python -m pytest -q matcher benchmark finetune
.\scripts\run_benchmark_windows.ps1 -Device cuda -Split val      # one model at a time; re-run to resume
```

Output: `benchmark/results/<run-id>/{config.json, predictions.jsonl, metrics.json, metrics.md}` and
`benchmark/results/COMPARISON_val.md`. With `-Dtype float32` (the default), decisions should match the CPU
runs except for small numerical differences. Only latency and memory should change. `bfloat16` is faster
but is a different configuration: give it its own run id.

VRAM: float32 weights of the largest candidate (Qwen3-0.6B) ≈ 2.4 GB, so it fits 6 GB with room for the KV cache.

## 5. Locked test split

Run it once, only for the configuration selected on val, plus the lexical baseline:

```powershell
python -m benchmark.run --backend transformers --model <selected> --revision <rev> --split test `
    --knowledge rag --device cuda --run-id <selected>-rag-test --i-understand-test-is-locked
```
