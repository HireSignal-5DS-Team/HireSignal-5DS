# Benchmark run: val_qwen2.5-0.5b+pilot-lora_rag

split `val` · backend `transformers` · knowledge `rag.bm25` · n = 110 requirements

| metric | final (after validation) | raw model |
|---|---|---|
| accuracy | 0.655 | 0.682 |
| macro-F1 | 0.629 | 0.657 |
| false-MET rate | 8.3% | 11.7% |
| UNCERTAIN recall | 0.522 | 0.522 |
| predicted UNCERTAIN share | 26.4% | 20.9% |
| unsupported MET | 0 | |
| JSON validity | | 99.1% |
| quote verbatim rate | | 86.8% (76 quotes) |

Evidence overlap on gold MET: 62.0% · basis accuracy on MISSING/MISSING: 88.9%
Latency: 6.791 s/req (max 13.09 s) · peak RSS 3624 MB (last process)

## Confusion (rows gold, columns final prediction)

| gold \ pred | MET | MISSING | UNCERTAIN |
|---|---|---|---|
| MET | 33 | 8 | 9 |
| MISSING | 2 | 27 | 8 |
| UNCERTAIN | 3 | 8 | 12 |

## Per class (final)

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| MET | 0.868 | 0.660 | 0.750 | 50 |
| MISSING | 0.628 | 0.730 | 0.675 | 37 |
| UNCERTAIN | 0.414 | 0.522 | 0.462 | 23 |

## Per tag accuracy (final)

| tag | n | accuracy |
|---|---|---|
| ambiguous_duration | 8 | 1.000 |
| certification | 15 | 0.667 |
| contradictory_requirement | 2 | 1.000 |
| education | 9 | 0.556 |
| equivalence | 17 | 0.765 |
| exact | 22 | 0.636 |
| experience_years | 12 | 0.167 |
| language | 7 | 0.286 |
| negation | 6 | 0.500 |
| not_documented | 18 | 1.000 |
| rag_only_term | 6 | 1.000 |
| related_not_equivalent | 21 | 0.762 |
