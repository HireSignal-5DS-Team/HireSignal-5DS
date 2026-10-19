# LoRA check — 30 bench-v1 val requirements (real-GPU, SMOKE TEST, not a benchmark)

Gold: MET 14, MISSING 9, UNCERTAIN 7. Seed 20261018, sampled from 202 val requirements. Server: b11139-42916d83f.

| arm | adapter scale | knowledge | valid JSON | accuracy | macro-F1 | false-MET | verbatim quotes | mean latency (s) |
|---|---|---|---|---|---|---|---|---|
| plain_k | none (no lora field) | BM25-ESCO k=3 | 0.900 | 0.633 | 0.647 | 0 | 22/22 | 1.41 |

30 items: one item = 3.3 accuracy points; differences of a few items are noise. Smoke test only.
