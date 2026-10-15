# Benchmark run: val_lfm2.5-350m_rag

split `val` · backend `transformers` · knowledge `rag.bm25` · n = 110 requirements

| metric | final (after validation) | raw model |
|---|---|---|
| accuracy | 0.273 | 0.118 |
| macro-F1 | 0.259 | 0.146 |
| false-MET rate | 8.3% | 13.3% |
| UNCERTAIN recall | 0.739 | 0.000 |
| predicted UNCERTAIN share | 72.7% | 0.0% |
| unsupported MET | 0 | |
| JSON validity | | 30.0% |
| quote verbatim rate | | 100.0% (26 quotes) |

Evidence overlap on gold MET: 4.0% · basis accuracy on MISSING/MISSING: 66.7%
Latency: 4.940 s/req (max 10.10 s) · peak RSS 2796 MB (last process)

## Confusion (rows gold, columns final prediction)

| gold \ pred | MET | MISSING | UNCERTAIN |
|---|---|---|---|
| MET | 4 | 8 | 38 |
| MISSING | 3 | 9 | 25 |
| UNCERTAIN | 2 | 4 | 17 |

## Per class (final)

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| MET | 0.444 | 0.080 | 0.136 | 50 |
| MISSING | 0.429 | 0.243 | 0.310 | 37 |
| UNCERTAIN | 0.212 | 0.739 | 0.330 | 23 |

## Per tag accuracy (final)

| tag | n | accuracy |
|---|---|---|
| ambiguous_duration | 8 | 0.875 |
| certification | 15 | 0.400 |
| contradictory_requirement | 2 | 1.000 |
| education | 9 | 0.222 |
| equivalence | 17 | 0.118 |
| exact | 22 | 0.227 |
| experience_years | 12 | 0.167 |
| language | 7 | 0.286 |
| negation | 6 | 0.500 |
| not_documented | 18 | 0.167 |
| rag_only_term | 6 | 0.000 |
| related_not_equivalent | 21 | 0.286 |
