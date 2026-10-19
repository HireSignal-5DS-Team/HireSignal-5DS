# LoRA check — 202 bench-v1 val requirements (real-GPU, full val split)

Gold: MET 86, MISSING 77, UNCERTAIN 39. All 202 val requirements. Server: b11139-42916d83f.

| arm | adapter scale | knowledge | valid JSON | accuracy | macro-F1 | false-MET | verbatim quotes | mean latency (s) |
|---|---|---|---|---|---|---|---|---|
| base_k | 0.0 | BM25-ESCO k=3 | 1.000 | 0.718 | 0.703 | 4 | 153/153 | 1.72 |
| lora_k | 1.0 | BM25-ESCO k=3 | 1.000 | 0.916 | 0.892 | 6 | 148/148 | 1.33 |

Constrained decoding: services\matcher\schema.json.

Per-class F1 and confusion matrix (rows = gold, columns = predicted):

**base_k**: F1 MET 0.861, MISSING 0.683, UNCERTAIN 0.567

| gold / pred | MET | MISSING | UNCERTAIN |
|---|---|---|---|
| MET | 68 | 3 | 15 |
| MISSING | 2 | 43 | 32 |
| UNCERTAIN | 2 | 3 | 34 |

**lora_k**: F1 MET 0.955, MISSING 0.920, UNCERTAIN 0.800

| gold / pred | MET | MISSING | UNCERTAIN |
|---|---|---|---|
| MET | 84 | 2 | 0 |
| MISSING | 2 | 75 | 0 |
| UNCERTAIN | 4 | 9 | 26 |

202 items: one item = 0.5 accuracy points. bench-v1 is SYNTHETIC (V2 generator), not real CVs.
