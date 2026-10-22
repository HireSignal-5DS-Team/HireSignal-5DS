# Consolidated Matcher comparison — split `val`

final = after deterministic validation; raw = the model's own decision. Gold UNCERTAIN share: 0.193. Explanation columns are deterministic proxies, not human ratings.

| run | model | adapter | params | macro-F1 | macro-F1 raw | false-MET | false-MET raw | MET P | MET R | JSON valid | quote valid | evidence attribution | UNCERTAIN rate | UNCERTAIN raw | expl. present | expl. on topic | review rate | p50 s | p95 s | RSS MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mock-gold-none-val | MOCK-gold (sanity check, not a model) | n/a | 0 (no model) | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.193 | 0.193 | 0.000 | 0.000 | 0.668 | 0.00 | 0.00 | 516.800 |
| mock-gold-rag-val | MOCK-gold (sanity check, not a model) | n/a | 0 (no model) | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.193 | 0.193 | 0.000 | 0.000 | 0.584 | 0.00 | 0.00 | 521.900 |
| qwen3-4b-q4+hslora-none-val | Qwen/Qwen3-4B-Instruct-2507+lora | n/a | n/a | 0.908 | 0.917 | 0.026 | 0.060 | 0.964 | 0.942 | 1.000 | 1.000 | 1.000 | 0.178 | 0.158 | 1.000 | 0.000 | 0.663 | 8.87 | 13.90 | 519.900 |
| qwen3-4b-q4+hslora-rag-val | Qwen/Qwen3-4B-Instruct-2507+lora | n/a | n/a | 0.897 | 0.903 | 0.034 | 0.060 | 0.955 | 0.977 | 1.000 | 1.000 | 1.000 | 0.153 | 0.139 | 1.000 | 0.000 | 0.574 | 13.09 | 21.46 | 524.100 |
| qwen3-4b-q4-none-val | Qwen/Qwen3-4B-Instruct-2507 | n/a | n/a | 0.634 | 0.641 | 0.009 | 0.026 | 0.981 | 0.616 | 0.950 | 1.000 | 0.857 | 0.495 | 0.436 | 0.950 | 0.847 | 0.782 | 12.94 | 20.75 | 517.400 |
| qwen3-4b-q4-rag-val | Qwen/Qwen3-4B-Instruct-2507 | n/a | n/a | 0.630 | 0.647 | 0.009 | 0.026 | 0.981 | 0.605 | 0.916 | 1.000 | 0.855 | 0.505 | 0.411 | 0.916 | 0.837 | 0.743 | 16.35 | 34.28 | 514.400 |
| lexical-rag-val | lexical_baseline | n/a | 0 (no model) | 0.436 | 0.436 | 0.560 | 0.560 | 0.508 | 0.779 | 1.000 | 1.000 | 0.944 | 0.000 | 0.000 | 1.000 | 0.000 | 0.381 | 0.00 | 0.00 | 522.100 |
| lexical-none-val | lexical_baseline | n/a | 0 (no model) | 0.373 | 0.373 | 0.560 | 0.560 | 0.435 | 0.581 | 1.000 | 1.000 | 0.931 | 0.000 | 0.000 | 1.000 | 0.000 | 0.446 | 0.00 | 0.00 | 516.400 |
| qwen2.5-0.5b-rag-val__schema_repair | Qwen/Qwen2.5-0.5B-Instruct | n/a | 494,032,768 | 0.265 | 0.386 | 0.009 | 0.345 | 0.800 | 0.047 | 1.000 | 0.067 | 0.071 | 0.460 | 0.074 | 0.614 | 0.574 | 0.827 | 5.97 | 12.50 | 3617.500 |
| qwen2.5-0.5b+kushal-lora-rag-val__schema_repair | Qwen/Qwen2.5-0.5B-Instruct | Kus-hal/resume-screener-lora | 494,032,768 | 0.245 | 0.226 | 0.000 | 0.000 | 0.000 | 0.000 | 0.926 | 0.543 | 0.227 | 0.554 | 0.480 | 0.030 | 0.020 | 0.946 | 9.41 | 19.72 | 3617.400 |
| qwen3-0.6b-rag-val | Qwen/Qwen3-0.6B | n/a | 596,049,920 | 0.222 | 0.122 | 0.000 | 0.000 | 0.000 | 0.000 | 0.203 | n/a | 0.000 | 0.906 | 0.109 | 0.203 | 0.183 | 0.980 | 10.23 | 15.28 | 5099.300 |
| qwen2.5-0.5b-rag-val | Qwen/Qwen2.5-0.5B-Instruct | n/a | 494,032,768 | 0.211 | 0.265 | 0.009 | 0.276 | 0.750 | 0.035 | 0.634 | 0.056 | 0.143 | 0.698 | 0.000 | 0.614 | 0.574 | 0.921 | 5.97 | 12.50 | 3617.500 |
| qwen2.5-0.5b+kushal-lora-rag-val | Qwen/Qwen2.5-0.5B-Instruct | Kus-hal/resume-screener-lora | 494,032,768 | 0.116 | 0.008 | 0.000 | 0.000 | 0.000 | 0.000 | 0.030 | 0.889 | 0.000 | 0.970 | 0.000 | 0.030 | 0.020 | 0.995 | 9.41 | 19.72 | 3617.400 |
| smollm2-360m-rag-val | HuggingFaceTB/SmolLM2-360M-Instruct | n/a | 361,821,120 | 0.108 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | n/a | n/a | 1.000 | 0.000 | 0.000 | 0.000 | 1.000 | 6.40 | 15.96 | 2792.100 |
