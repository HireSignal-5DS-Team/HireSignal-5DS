# Benchmark run: val_granite-4.0-350m_rag

split `val` · backend `transformers` · knowledge `rag.bm25` · n = 110 requirements

| metric | final (after validation) | raw model |
|---|---|---|
| accuracy | 0.209 | 0.000 |
| macro-F1 | 0.115 | 0.000 |
| false-MET rate | 0.0% | 0.0% |
| UNCERTAIN recall | 1.000 | 0.000 |
| predicted UNCERTAIN share | 100.0% | 0.9% |
| unsupported MET | 0 | |
| JSON validity | | 0.9% |
| quote verbatim rate | | n/a (0 quotes) |

Evidence overlap on gold MET: 0.0% · basis accuracy on MISSING/MISSING: n/a
Latency: 6.930 s/req (max 13.70 s) · peak RSS 2814 MB (last process)

## Confusion (rows gold, columns final prediction)

| gold \ pred | MET | MISSING | UNCERTAIN |
|---|---|---|---|
| MET | 0 | 0 | 50 |
| MISSING | 0 | 0 | 37 |
| UNCERTAIN | 0 | 0 | 23 |

## Per class (final)

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| MET | n/a | 0.000 | 0.000 | 50 |
| MISSING | n/a | 0.000 | 0.000 | 37 |
| UNCERTAIN | 0.209 | 1.000 | 0.346 | 23 |

## Per tag accuracy (final)

| tag | n | accuracy |
|---|---|---|
| ambiguous_duration | 8 | 1.000 |
| certification | 15 | 0.067 |
| contradictory_requirement | 2 | 1.000 |
| education | 9 | 0.111 |
| equivalence | 17 | 0.118 |
| exact | 22 | 0.136 |
| experience_years | 12 | 0.167 |
| language | 7 | 0.286 |
| negation | 6 | 0.000 |
| not_documented | 18 | 0.000 |
| rag_only_term | 6 | 0.000 |
| related_not_equivalent | 21 | 0.238 |
