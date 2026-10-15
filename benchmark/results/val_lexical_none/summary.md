# Benchmark run: val_lexical_none

split `val` · backend `lexical_baseline` · knowledge `none` · n = 110 requirements

| metric | final (after validation) | raw model |
|---|---|---|
| accuracy | 0.482 | 0.482 |
| macro-F1 | 0.355 | 0.355 |
| false-MET rate | 36.7% | 36.7% |
| UNCERTAIN recall | 0.000 | 0.000 |
| predicted UNCERTAIN share | 0.0% | 0.0% |
| unsupported MET | 0 | |
| JSON validity | | 100.0% |
| quote verbatim rate | | 100.0% (49 quotes) |

Evidence overlap on gold MET: 44.0% · basis accuracy on MISSING/MISSING: 84.6%
Latency: 0.000 s/req (max 0.00 s) · peak RSS 26 MB (last process)

## Confusion (rows gold, columns final prediction)

| gold \ pred | MET | MISSING | UNCERTAIN |
|---|---|---|---|
| MET | 27 | 23 | 0 |
| MISSING | 13 | 26 | 0 |
| UNCERTAIN | 9 | 12 | 0 |

## Per class (final)

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| MET | 0.551 | 0.540 | 0.545 | 50 |
| MISSING | 0.426 | 0.667 | 0.520 | 39 |
| UNCERTAIN | n/a | 0.000 | 0.000 | 21 |

## Per tag accuracy (final)

| tag | n | accuracy |
|---|---|---|
| ambiguous_duration | 7 | 0.000 |
| certification | 15 | 0.600 |
| contradictory_requirement | 2 | 0.000 |
| education | 9 | 0.444 |
| equivalence | 17 | 0.118 |
| exact | 22 | 0.682 |
| experience_years | 12 | 0.500 |
| language | 7 | 0.286 |
| negation | 6 | 0.000 |
| not_documented | 19 | 1.000 |
| rag_only_term | 6 | 0.333 |
| related_not_equivalent | 21 | 0.762 |

Note: backend `lexical_baseline` is not a neural model.
