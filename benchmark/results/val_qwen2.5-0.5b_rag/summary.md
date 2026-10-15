# Benchmark run: val_qwen2.5-0.5b_rag

split `val` · backend `transformers` · knowledge `rag.bm25` · n = 110 requirements

| metric | final (after validation) | raw model |
|---|---|---|
| accuracy | 0.291 | 0.373 |
| macro-F1 | 0.248 | 0.305 |
| false-MET rate | 0.0% | 30.0% |
| UNCERTAIN recall | 0.522 | 0.000 |
| predicted UNCERTAIN share | 51.8% | 0.0% |
| unsupported MET | 0 | |
| JSON validity | | 83.6% |
| quote verbatim rate | | 100.0% (2 quotes) |

Evidence overlap on gold MET: 0.0% · basis accuracy on MISSING/MISSING: 55.0%
Latency: 5.226 s/req (max 11.15 s) · peak RSS 3623 MB (last process)

## Confusion (rows gold, columns final prediction)

| gold \ pred | MET | MISSING | UNCERTAIN |
|---|---|---|---|
| MET | 0 | 22 | 28 |
| MISSING | 0 | 20 | 17 |
| UNCERTAIN | 0 | 11 | 12 |

## Per class (final)

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| MET | n/a | 0.000 | 0.000 | 50 |
| MISSING | 0.377 | 0.541 | 0.444 | 37 |
| UNCERTAIN | 0.211 | 0.522 | 0.300 | 23 |

## Per tag accuracy (final)

| tag | n | accuracy |
|---|---|---|
| ambiguous_duration | 8 | 0.500 |
| certification | 15 | 0.467 |
| contradictory_requirement | 2 | 0.500 |
| education | 9 | 0.333 |
| equivalence | 17 | 0.059 |
| exact | 22 | 0.091 |
| experience_years | 12 | 0.083 |
| language | 7 | 0.286 |
| negation | 6 | 0.667 |
| not_documented | 18 | 0.500 |
| rag_only_term | 6 | 0.167 |
| related_not_equivalent | 21 | 0.619 |
