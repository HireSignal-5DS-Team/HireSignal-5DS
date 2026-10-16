# RAG ↔ Qwen3-4B Matcher integration tests

The Matcher (branch `claude/kind-albattani-k7qlt9`, code used unmodified from a read-only checkout) asks the RAG for
ESCO knowledge per requirement and classifies it as MET / MISSING / UNCERTAIN; the RAG never decides.

| File | Purpose |
|---|---|
| `run_matcher_rag.py` | runs the Matcher's own benchmark (`benchmark.run`) with `--rag none / bm25 / dense`; every other argument is passed through (backend, model, adapter, split, run id) |
| `compare_matcher.py` | metrics with the Matcher's own `benchmark.metrics.compute` + paired McNemar and bootstrap CI of macro-F1 |
| `results/` | predictions, metrics and configs of runs made from this branch |

## Configurations

| | Knowledge provider | Retriever |
|---|---|---|
| A | none | — |
| B | the Matcher's `RagKnowledge` (BM25 over the 1,621 ESCO concepts, query = requirement skill terms), reading this branch's `rag/` | `rag.bm25` |
| C | `DenseKnowledge` in `run_matcher_rag.py`: same collection, same query text, same k = 3, e5-small dense, persisted index | `rag.dense.e5-small` |

## Commands (local llama.cpp server, CPU)

```bash
llama-server -m Qwen3-4B-Instruct-2507-Q4_K_M.gguf --alias Qwen/Qwen3-4B-Instruct-2507 -c 4096 -t 4 -np 1 --jinja --port 8080
export MATCHER_DIR=/path/to/checkout/of/claude/kind-albattani-k7qlt9 HF_HUB_OFFLINE=1
python rag/integration/run_matcher_rag.py --rag dense -- --backend openai --base-url http://127.0.0.1:8080/v1 \
  --model Qwen/Qwen3-4B-Instruct-2507 --revision "<gguf revision>" --split val --run-id qwen3-4b-q4-dense-val \
  --out-root rag/integration/results
python rag/integration/compare_matcher.py <A_dir> <B_dir> <C_dir>
```

## Fine-tuned model (Dali's LoRA) — prepared, NOT run

The adapter does not exist yet; nothing below has been executed. Because `run_matcher_rag.py` forwards all
arguments, the four-way comparison needs no RAG-side change:

| Run | Command difference |
|---|---|
| 1. base, no RAG | `--rag none` |
| 2. base + RAG | `--rag dense` (or `bm25`) |
| 3. LoRA, no RAG | `--rag none -- --backend transformers --model Qwen/Qwen3-4B-Instruct-2507 --adapter <adapter dir>` (4-bit GPU load, as in Dali's `eval_val.py`), or llama.cpp with the adapter converted to GGUF and `llama-server --lora <file>` |
| 4. LoRA + RAG | same as 3 with `--rag dense` |

Compare 1↔3 and 2↔4 only under identical serving (same quantisation, backend and prompt); the existing A/B numbers
use llama.cpp Q4_K_M on CPU, the LoRA evaluation is planned with transformers 4-bit on GPU, which is not comparable.
