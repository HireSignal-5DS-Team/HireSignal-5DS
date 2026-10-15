# Benchmark comparison

Final = after deterministic validation; raw = model decision before validation. Non-model backends (lexical, mock) are references, not SLM results.

| arm | split | backend | knowledge | n | macro-F1 | acc | false-MET rate | raw macro-F1 | JSON validity | quote verbatim | sec/req | peak RSS MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| val_lexical_none | val | lexical_baseline | none | 110 | 0.355 | 0.482 | 36.7% | 0.355 | 100.0% | 100.0% | 0.000 | 26 |
| val_lexical_rag | val | lexical_baseline | rag.bm25 | 110 | 0.359 | 0.491 | 46.7% | 0.359 | 100.0% | 100.0% | 0.001 | 54 |
