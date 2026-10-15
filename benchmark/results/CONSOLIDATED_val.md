# Consolidated Matcher comparison — split `val`

final = after deterministic validation; raw = the model's own decision. Gold UNCERTAIN share: 0.193. Explanation columns are deterministic proxies, not human ratings.

| run | model | adapter | params | macro-F1 | macro-F1 raw | false-MET | false-MET raw | MET P | MET R | JSON valid | quote valid | evidence attribution | UNCERTAIN rate | UNCERTAIN raw | expl. present | expl. on topic | review rate | p50 s | p95 s | RSS MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mock-gold-none-val | MOCK-gold (sanity check, not a model) | n/a | 0 (no model) | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.193 | 0.193 | 0.000 | 0.000 | 0.668 | 0.00 | 0.00 | 516.800 |
| mock-gold-rag-val | MOCK-gold (sanity check, not a model) | n/a | 0 (no model) | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.193 | 0.193 | 0.000 | 0.000 | 0.584 | 0.00 | 0.00 | 521.900 |
| lexical-rag-val | lexical_baseline | n/a | 0 (no model) | 0.436 | 0.436 | 0.560 | 0.560 | 0.508 | 0.779 | 1.000 | 1.000 | 0.944 | 0.000 | 0.000 | 1.000 | 0.000 | 0.381 | 0.00 | 0.00 | 522.100 |
| lexical-none-val | lexical_baseline | n/a | 0 (no model) | 0.373 | 0.373 | 0.560 | 0.560 | 0.435 | 0.581 | 1.000 | 1.000 | 0.931 | 0.000 | 0.000 | 1.000 | 0.000 | 0.446 | 0.00 | 0.00 | 516.400 |
| qwen2.5-0.5b-rag-val | Qwen/Qwen2.5-0.5B-Instruct | n/a | 494,032,768 | 0.211 | 0.265 | 0.009 | 0.276 | 0.750 | 0.035 | 0.634 | 0.056 | 0.143 | 0.698 | 0.000 | 0.614 | 0.574 | 0.921 | 5.97 | 12.50 | 3617.500 |
