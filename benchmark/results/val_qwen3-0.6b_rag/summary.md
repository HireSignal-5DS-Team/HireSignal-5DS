# Benchmark run: val_qwen3-0.6b_rag

split `val` · backend `transformers` · knowledge `rag.bm25` · n = 110 requirements

| metric | final (after validation) | raw model |
|---|---|---|
| accuracy | 0.300 | 0.300 |
| macro-F1 | 0.272 | 0.267 |
| false-MET rate | 1.7% | 1.7% |
| UNCERTAIN recall | 0.913 | 0.000 |
| predicted UNCERTAIN share | 81.8% | 0.0% |
| unsupported MET | 0 | |
| JSON validity | | 62.7% |
| quote verbatim rate | | 88.9% (18 quotes) |

Evidence overlap on gold MET: 6.0% · basis accuracy on MISSING/MISSING: 20.0%
Latency: 9.720 s/req (max 16.87 s) · peak RSS 5106 MB (last process)

## Confusion (rows gold, columns final prediction)

| gold \ pred | MET | MISSING | UNCERTAIN |
|---|---|---|---|
| MET | 7 | 6 | 37 |
| MISSING | 0 | 5 | 32 |
| UNCERTAIN | 1 | 1 | 21 |

## Per class (final)

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| MET | 0.875 | 0.140 | 0.241 | 50 |
| MISSING | 0.417 | 0.135 | 0.204 | 37 |
| UNCERTAIN | 0.233 | 0.913 | 0.372 | 23 |

## Per tag accuracy (final)

| tag | n | accuracy |
|---|---|---|
| ambiguous_duration | 8 | 1.000 |
| certification | 15 | 0.400 |
| contradictory_requirement | 2 | 1.000 |
| education | 9 | 0.111 |
| equivalence | 17 | 0.176 |
| exact | 22 | 0.227 |
| experience_years | 12 | 0.333 |
| language | 7 | 0.286 |
| negation | 6 | 0.667 |
| not_documented | 18 | 0.000 |
| rag_only_term | 6 | 0.000 |
| related_not_equivalent | 21 | 0.286 |
