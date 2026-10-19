# Notes — schema check 2026-10-18 (real-GPU, RTX 4050 Laptop 6 GB, llama.cpp b11139-42916d83f CUDA 12.4)

Same 30 items, prompt (matcher-v1), knowledge (BM25-ESCO k=3) and decoding as `../2026-10-18_lora_check/`.
Only change: each request carries `response_format: {"type": "json_object", "schema": <services/matcher/schema.json>}`.
llama-server compiles the schema to a grammar (b11139 `tools/server/README.md` line 1316), so decision/basis can
only be valid labels and the reply is always one JSON object with the 4 keys.

Grammar check before the run: the prompt "Write one short sentence about cats. No JSON." returned plain text
without the schema and a schema-shaped JSON object with it.

`diff_vs_lora_check.txt` (`scripts/diff_arms.py`): item-by-item, no schema vs schema.
- base_k: identical raw output 27/30; the 3 changed items are exactly the 3 invalid template-copy replies, now valid and all = gold.
- lora_k: identical raw output 30/30.

Smoke test, 30 items: one item = 3.3 accuracy points.
