# LoRA check — 30 bench-v1 val requirements (real-GPU, SMOKE TEST, not a benchmark)

Gold: MET 14, MISSING 9, UNCERTAIN 7. Seed 20261018, sampled from 202 val requirements. Server: b11139-42916d83f.

| arm | adapter scale | knowledge | valid JSON | accuracy | macro-F1 | false-MET | verbatim quotes | mean latency (s) |
|---|---|---|---|---|---|---|---|---|
| base_k | 0.0 | BM25-ESCO k=3 | 1.000 | 0.733 | 0.728 | 0 | 25/25 | 1.81 |
| lora_k | 1.0 | BM25-ESCO k=3 | 1.000 | 0.933 | 0.911 | 0 | 24/24 | 1.47 |

Constrained decoding: services\matcher\schema.json.

Per-class F1 and confusion matrix (rows = gold, columns = predicted):

**base_k**: F1 MET 0.833, MISSING 0.714, UNCERTAIN 0.636

| gold \ pred | MET | MISSING | UNCERTAIN |
|---|---|---|---|
| MET | 10 | 0 | 4 |
| MISSING | 0 | 5 | 4 |
| UNCERTAIN | 0 | 0 | 7 |

**lora_k**: F1 MET 1.000, MISSING 0.900, UNCERTAIN 0.833

| gold \ pred | MET | MISSING | UNCERTAIN |
|---|---|---|---|
| MET | 14 | 0 | 0 |
| MISSING | 0 | 9 | 0 |
| UNCERTAIN | 0 | 2 | 5 |

30 items: one item = 3.3 accuracy points. bench-v1 is SYNTHETIC (V2 generator), not real CVs.
