# Benchmark run: val_smollm2-360m_rag

split `val` · backend `transformers` · knowledge `rag.bm25` · n = 110 requirements

| metric | final (after validation) | raw model |
|---|---|---|
| accuracy | 0.300 | 0.264 |
| macro-F1 | 0.236 | 0.162 |
| false-MET rate | 55.0% | 66.7% |
| UNCERTAIN recall | 0.522 | 0.000 |
| predicted UNCERTAIN share | 50.9% | 0.0% |
| unsupported MET | 0 | |
| JSON validity | | 63.6% |
| quote verbatim rate | | 82.4% (136 quotes) |

Evidence overlap on gold MET: 8.0% · basis accuracy on MISSING/MISSING: n/a
Latency: 9.378 s/req (max 15.76 s) · peak RSS 2798 MB (last process)

## Confusion (rows gold, columns final prediction)

| gold \ pred | MET | MISSING | UNCERTAIN |
|---|---|---|---|
| MET | 21 | 0 | 29 |
| MISSING | 22 | 0 | 15 |
| UNCERTAIN | 11 | 0 | 12 |

## Per class (final)

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| MET | 0.389 | 0.420 | 0.404 | 50 |
| MISSING | n/a | 0.000 | 0.000 | 37 |
| UNCERTAIN | 0.214 | 0.522 | 0.304 | 23 |

## Per tag accuracy (final)

| tag | n | accuracy |
|---|---|---|
| ambiguous_duration | 8 | 0.875 |
| certification | 15 | 0.067 |
| contradictory_requirement | 2 | 1.000 |
| education | 9 | 0.222 |
| equivalence | 17 | 0.353 |
| exact | 22 | 0.455 |
| experience_years | 12 | 0.333 |
| language | 7 | 0.286 |
| negation | 6 | 0.000 |
| not_documented | 18 | 0.000 |
| rag_only_term | 6 | 0.167 |
| related_not_equivalent | 21 | 0.048 |
