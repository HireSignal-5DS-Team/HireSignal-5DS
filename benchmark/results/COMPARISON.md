# Benchmark comparison

Final = after deterministic validation; raw = model decision before validation. Non-model backends (lexical, mock) are references, not SLM results.

| arm | split | backend | knowledge | n | macro-F1 | acc | false-MET rate | raw macro-F1 | JSON validity | quote verbatim | sec/req | peak RSS MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| val_granite-4.0-350m_rag | val | transformers | rag.bm25 | 110 | 0.115 | 0.209 | 0.0% | 0.000 | 0.9% | n/a | 6.930 | 2814 |
| val_lexical_none | val | lexical_baseline | none | 110 | 0.488 | 0.527 | 13.3% | 0.359 | 100.0% | 100.0% | 0.000 | 26 |
| val_lexical_rag | val | lexical_baseline | rag.bm25 | 110 | 0.507 | 0.545 | 20.0% | 0.363 | 100.0% | 100.0% | 0.001 | 53 |
| val_lfm2-350m_rag | val | transformers | rag.bm25 | 110 | 0.115 | 0.209 | 0.0% | 0.000 | 0.0% | n/a | 7.856 | 2789 |
| val_lfm2.5-350m_rag | val | transformers | rag.bm25 | 110 | 0.259 | 0.273 | 8.3% | 0.146 | 30.0% | 100.0% | 4.940 | 2796 |
| val_qwen2.5-0.5b+kushal-lora_rag | val | transformers | rag.bm25 | 110 | 0.256 | 0.300 | 0.0% | 0.137 | 54.5% | 74.7% | 7.996 | 3625 |
| val_qwen2.5-0.5b+pilot-lora_none | val | transformers | none | 110 | 0.629 | 0.655 | 8.3% | 0.648 | 99.1% | 86.7% | 6.154 | 3620 |
| val_qwen2.5-0.5b+pilot-lora_rag | val | transformers | rag.bm25 | 110 | 0.629 | 0.655 | 8.3% | 0.657 | 99.1% | 86.8% | 6.791 | 3624 |
| val_qwen2.5-0.5b_rag | val | transformers | rag.bm25 | 110 | 0.248 | 0.291 | 0.0% | 0.305 | 83.6% | 100.0% | 5.226 | 3623 |
| val_qwen3-0.6b_rag | val | transformers | rag.bm25 | 110 | 0.272 | 0.300 | 1.7% | 0.267 | 62.7% | 88.9% | 9.720 | 5106 |
| val_qwen3.5-0.8b_rag | val | transformers | rag.bm25 | 110 | 0.486 | 0.618 | 21.7% | 0.463 | 99.1% | 84.8% | 15.341 | 5408 |
| val_smollm2-360m_rag | val | transformers | rag.bm25 | 110 | 0.236 | 0.300 | 55.0% | 0.162 | 63.6% | 82.4% | 9.378 | 2798 |
