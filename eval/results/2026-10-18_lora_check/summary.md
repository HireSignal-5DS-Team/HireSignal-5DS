# LoRA check — 30 bench-v1 val requirements (real-GPU, SMOKE TEST, not a benchmark)

Gold: MET 14, MISSING 9, UNCERTAIN 7. Seed 20261018, sampled from 202 val requirements. Server: b11139-42916d83f.

| arm | adapter scale | knowledge | valid JSON | accuracy | macro-F1 | false-MET | verbatim quotes | mean latency (s) |
|---|---|---|---|---|---|---|---|---|
| base_k | 0.0 | BM25-ESCO k=3 | 0.900 | 0.633 | 0.647 | 0 | 22/22 | 1.42 |
| lora_k | 1.0 | BM25-ESCO k=3 | 1.000 | 0.933 | 0.911 | 0 | 24/24 | 1.15 |
| base_0 | 0.0 | none | 0.933 | 0.600 | 0.618 | 0 | 22/22 | 1.32 |
| lora_0 | 1.0 | none | 1.000 | 0.900 | 0.880 | 1 | 24/24 | 1.09 |

30 items: one item = 3.3 accuracy points; differences of a few items are noise. Smoke test only.
