# Benchmark run: TEST_lexical_rag

split `test` · backend `lexical_baseline` · knowledge `rag.bm25` · n = 112 requirements

| metric | final (after validation) | raw model |
|---|---|---|
| accuracy | 0.571 | 0.580 |
| macro-F1 | 0.469 | 0.421 |
| false-MET rate | 20.7% | 34.5% |
| UNCERTAIN recall | 0.100 | 0.000 |
| predicted UNCERTAIN share | 9.8% | 0.0% |
| unsupported MET | 0 | |
| JSON validity | | 100.0% |
| quote verbatim rate | | 100.0% (63 quotes) |

Evidence overlap on gold MET: 61.1% · basis accuracy on MISSING/MISSING: 76.9%
Latency: 0.001 s/req (max 0.01 s) · peak RSS 54 MB (last process)

## Confusion (rows gold, columns final prediction)

| gold \ pred | MET | MISSING | UNCERTAIN |
|---|---|---|---|
| MET | 36 | 15 | 3 |
| MISSING | 6 | 26 | 6 |
| UNCERTAIN | 6 | 12 | 2 |

## Per class (final)

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| MET | 0.750 | 0.667 | 0.706 | 54 |
| MISSING | 0.491 | 0.684 | 0.571 | 38 |
| UNCERTAIN | 0.182 | 0.100 | 0.129 | 20 |

## Per tag accuracy (final)

| tag | n | accuracy |
|---|---|---|
| ambiguous_duration | 4 | 0.250 |
| certification | 8 | 0.625 |
| contradictory_requirement | 2 | 0.500 |
| education | 10 | 0.500 |
| equivalence | 12 | 0.333 |
| exact | 26 | 0.692 |
| experience_years | 15 | 0.400 |
| language | 9 | 0.556 |
| negation | 9 | 0.333 |
| not_documented | 21 | 0.905 |
| rag_only_term | 4 | 0.250 |
| related_not_equivalent | 21 | 0.619 |

Note: backend `lexical_baseline` is not a neural model.
