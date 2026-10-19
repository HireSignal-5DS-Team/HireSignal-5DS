# Notes — LoRA check 2026-10-18 (real-GPU, RTX 4050 Laptop 6 GB, llama.cpp b11139-42916d83f CUDA 12.4)

Smoke test on 30 items, **not a benchmark**: one item = 3.3 accuracy points.

## Files
- `summary.md`: main table (4 arms).
- `items.json`: the fixed list of 30 (case_id, req_id, gold, rag_refs).
- `<arm>.jsonl`: per-item outputs.
- `config.json`: run configuration.

## Server setup
- One Qwen3-4B Q4_K_M base with the LoRA loaded (`--lora models/hiresignal-lora-f16.gguf --lora-init-without-apply`). The global scale is set to 0 at startup (`scripts/start_llm.ps1`).
- Each request picks the adapter with `"lora": [{"id": 0, "scale": 0|1}]`.
- `cache_prompt: false`, so no KV cache is reused across adapter scales.

## Per-request switching checks (ad hoc, before the run)
- Same Matcher prompt (3 items) with scale 0 vs scale 1: the outputs differ, and repeated scale-0 calls are identical.
- **b11139 behaviour:**
  - With `--lora-init-without-apply` alone, `/lora-adapters` reports `scale: 1.0`.
  - A request **without** a `lora` field got the LoRA output (identical to scale 1 on 3/3 items).
  - After `POST /lora-adapters [{"id":0,"scale":0}]`, a request without the field equals scale 0. This holds even right after a scale-1 request.
  - `start_llm.ps1` now does this POST.

## Scale 0 == plain model
- `plain_server/` holds the same 30 items with BM25-ESCO k=3, on a server started **without** `--lora` (`start_llm.ps1 -NoLora`).
- `plain_server/parity.txt`: identical raw output 30/30 vs `base_k.jsonl` (scale 0, LoRA loaded).

## Parity with V2 (offline, `scripts/check_matcher_parity.py`)
- The system prompt is identical to V2 p1.
- User messages are identical to V2 `user_message()` on 30/30 items.
- Retrieved ESCO ids are identical to V2's logged `rag_refs` (`qwen3-4b-q4-rag-val`) on 30/30 items.

## VRAM
- 3255 MiB / 6141 MiB with the server loaded (n_gpu_layers all, ctx 4096); 3259 MiB during inference.
- Ollama has no model loaded.
