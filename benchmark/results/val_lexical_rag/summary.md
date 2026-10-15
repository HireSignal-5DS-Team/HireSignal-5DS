# Benchmark run: val_lexical_rag

split `val` · backend `lexical_baseline` · knowledge `rag.bm25` · n = 110 requirements

| metric | final (after validation) | raw model |
|---|---|---|
| accuracy | 0.491 | 0.491 |
| macro-F1 | 0.359 | 0.359 |
| false-MET rate | 46.7% | 46.7% |
| UNCERTAIN recall | 0.000 | 0.000 |
| predicted UNCERTAIN share | 0.0% | 0.0% |
| unsupported MET | 0 | |
| JSON validity | | 100.0% |
| quote verbatim rate | | 100.0% (60 quotes) |

Evidence overlap on gold MET: 54.0% · basis accuracy on MISSING/MISSING: 86.4%
Latency: 0.001 s/req (max 0.01 s) · peak RSS 54 MB (last process)

## Confusion (rows gold, columns final prediction)

| gold \ pred | MET | MISSING | UNCERTAIN |
|---|---|---|---|
| MET | 32 | 18 | 0 |
| MISSING | 17 | 22 | 0 |
| UNCERTAIN | 11 | 10 | 0 |

## Per class (final)

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| MET | 0.533 | 0.640 | 0.582 | 50 |
| MISSING | 0.440 | 0.564 | 0.494 | 39 |
| UNCERTAIN | n/a | 0.000 | 0.000 | 21 |

## Per tag accuracy (final)

| tag | n | accuracy |
|---|---|---|
| ambiguous_duration | 7 | 0.000 |
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
| related_not_equivalent | 21 | 0.762 |

Note: backend `lexical_baseline` is not a neural model.
