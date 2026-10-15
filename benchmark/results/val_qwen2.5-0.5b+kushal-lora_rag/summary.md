# Benchmark run: val_qwen2.5-0.5b+kushal-lora_rag

split `val` · backend `transformers` · knowledge `rag.bm25` · n = 110 requirements

| metric | final (after validation) | raw model |
|---|---|---|
| accuracy | 0.300 | 0.182 |
| macro-F1 | 0.256 | 0.137 |
| false-MET rate | 0.0% | 0.0% |
| UNCERTAIN recall | 0.565 | 0.000 |
| predicted UNCERTAIN share | 45.5% | 0.0% |
| unsupported MET | 0 | |
| JSON validity | | 54.5% |
| quote verbatim rate | | 74.7% (87 quotes) |

Evidence overlap on gold MET: 22.0% · basis accuracy on MISSING/MISSING: 55.0%
Latency: 7.996 s/req (max 17.16 s) · peak RSS 3625 MB (last process)

## Confusion (rows gold, columns final prediction)

| gold \ pred | MET | MISSING | UNCERTAIN |
|---|---|---|---|
| MET | 0 | 30 | 20 |
| MISSING | 0 | 20 | 17 |
| UNCERTAIN | 0 | 10 | 13 |

## Per class (final)

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| MET | n/a | 0.000 | 0.000 | 50 |
| MISSING | 0.333 | 0.541 | 0.412 | 37 |
| UNCERTAIN | 0.260 | 0.565 | 0.356 | 23 |

## Per tag accuracy (final)

| tag | n | accuracy |
|---|---|---|
| ambiguous_duration | 8 | 0.500 |
| certification | 15 | 0.333 |
| contradictory_requirement | 2 | 0.000 |
| education | 9 | 0.222 |
| equivalence | 17 | 0.118 |
| exact | 22 | 0.091 |
| experience_years | 12 | 0.333 |
| language | 7 | 0.429 |
| negation | 6 | 0.667 |
| not_documented | 18 | 0.500 |
| rag_only_term | 6 | 0.167 |
| related_not_equivalent | 21 | 0.524 |
