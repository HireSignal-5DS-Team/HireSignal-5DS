# Benchmark run: val_qwen3.5-0.8b_rag

split `val` · backend `transformers` · knowledge `rag.bm25` · n = 110 requirements

| metric | final (after validation) | raw model |
|---|---|---|
| accuracy | 0.618 | 0.627 |
| macro-F1 | 0.486 | 0.463 |
| false-MET rate | 21.7% | 25.0% |
| UNCERTAIN recall | 0.048 | 0.000 |
| predicted UNCERTAIN share | 4.5% | 0.0% |
| unsupported MET | 0 | |
| JSON validity | | 99.1% |
| quote verbatim rate | | 84.8% (145 quotes) |

Evidence overlap on gold MET: 50.0% · basis accuracy on MISSING/MISSING: 64.5%
Latency: 15.341 s/req (max 38.17 s) · peak RSS 5408 MB (last process)

## Confusion (rows gold, columns final prediction)

| gold \ pred | MET | MISSING | UNCERTAIN |
|---|---|---|---|
| MET | 36 | 11 | 3 |
| MISSING | 7 | 31 | 1 |
| UNCERTAIN | 6 | 14 | 1 |

## Per class (final)

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| MET | 0.735 | 0.720 | 0.727 | 50 |
| MISSING | 0.554 | 0.795 | 0.653 | 39 |
| UNCERTAIN | 0.200 | 0.048 | 0.077 | 21 |

## Per tag accuracy (final)

| tag | n | accuracy |
|---|---|---|
| ambiguous_duration | 7 | 0.000 |
| certification | 15 | 0.733 |
| contradictory_requirement | 2 | 0.000 |
| education | 9 | 0.778 |
| equivalence | 17 | 0.647 |
| exact | 22 | 0.682 |
| experience_years | 12 | 0.417 |
| language | 7 | 0.571 |
| negation | 6 | 0.500 |
| not_documented | 19 | 0.895 |
| rag_only_term | 6 | 0.500 |
| related_not_equivalent | 21 | 0.714 |
