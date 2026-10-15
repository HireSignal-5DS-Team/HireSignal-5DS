# Benchmark run: val_lexical_rag

split `val` · backend `lexical_baseline` · knowledge `rag.bm25` · n = 110 requirements

| metric | final (after validation) | raw model |
|---|---|---|
| accuracy | 0.536 | 0.491 |
| macro-F1 | 0.499 | 0.359 |
| false-MET rate | 30.0% | 46.7% |
| UNCERTAIN recall | 0.286 | 0.000 |
| predicted UNCERTAIN share | 10.0% | 0.0% |
| unsupported MET | 0 | |
| JSON validity | | 100.0% |
| quote verbatim rate | | 100.0% (60 quotes) |

Evidence overlap on gold MET: 54.0% · basis accuracy on MISSING/MISSING: 86.4%
Latency: 0.001 s/req (max 0.01 s) · peak RSS 54 MB (last process)

## Confusion (rows gold, columns final prediction)

| gold \ pred | MET | MISSING | UNCERTAIN |
|---|---|---|---|
| MET | 31 | 18 | 1 |
| MISSING | 13 | 22 | 4 |
| UNCERTAIN | 5 | 10 | 6 |

## Per class (final)

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| MET | 0.633 | 0.620 | 0.626 | 50 |
| MISSING | 0.440 | 0.564 | 0.494 | 39 |
| UNCERTAIN | 0.545 | 0.286 | 0.375 | 21 |

## Per tag accuracy (final)

| tag | n | accuracy |
|---|---|---|
| ambiguous_duration | 7 | 0.714 |
| certification | 15 | 0.533 |
| contradictory_requirement | 2 | 0.000 |
| education | 9 | 0.444 |
| equivalence | 17 | 0.353 |
| exact | 22 | 0.682 |
| experience_years | 12 | 0.417 |
| language | 7 | 0.286 |
| negation | 6 | 0.000 |
| not_documented | 19 | 0.842 |
| rag_only_term | 6 | 0.500 |
| related_not_equivalent | 21 | 0.810 |

Note: backend `lexical_baseline` is not a neural model.
