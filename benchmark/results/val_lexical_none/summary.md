# Benchmark run: val_lexical_none

split `val` · backend `lexical_baseline` · knowledge `none` · n = 110 requirements

| metric | final (after validation) | raw model |
|---|---|---|
| accuracy | 0.527 | 0.482 |
| macro-F1 | 0.488 | 0.359 |
| false-MET rate | 13.3% | 36.7% |
| UNCERTAIN recall | 0.261 | 0.000 |
| predicted UNCERTAIN share | 13.6% | 0.0% |
| unsupported MET | 0 | |
| JSON validity | | 100.0% |
| quote verbatim rate | | 100.0% (49 quotes) |

Evidence overlap on gold MET: 44.0% · basis accuracy on MISSING/MISSING: 80.8%
Latency: 0.000 s/req (max 0.00 s) · peak RSS 26 MB (last process)

## Confusion (rows gold, columns final prediction)

| gold \ pred | MET | MISSING | UNCERTAIN |
|---|---|---|---|
| MET | 26 | 23 | 1 |
| MISSING | 3 | 26 | 8 |
| UNCERTAIN | 5 | 12 | 6 |

## Per class (final)

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| MET | 0.765 | 0.520 | 0.619 | 50 |
| MISSING | 0.426 | 0.703 | 0.531 | 37 |
| UNCERTAIN | 0.400 | 0.261 | 0.316 | 23 |

## Per tag accuracy (final)

| tag | n | accuracy |
|---|---|---|
| ambiguous_duration | 8 | 0.750 |
| certification | 15 | 0.600 |
| contradictory_requirement | 2 | 0.000 |
| education | 9 | 0.444 |
| equivalence | 17 | 0.118 |
| exact | 22 | 0.682 |
| experience_years | 12 | 0.583 |
| language | 7 | 0.286 |
| negation | 6 | 0.000 |
| not_documented | 18 | 1.000 |
| rag_only_term | 6 | 0.333 |
| related_not_equivalent | 21 | 0.762 |

Note: backend `lexical_baseline` is not a neural model.
