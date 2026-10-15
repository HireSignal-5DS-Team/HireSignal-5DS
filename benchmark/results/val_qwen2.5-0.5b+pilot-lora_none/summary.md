# Benchmark run: val_qwen2.5-0.5b+pilot-lora_none

split `val` · backend `transformers` · knowledge `none` · n = 110 requirements

| metric | final (after validation) | raw model |
|---|---|---|
| accuracy | 0.655 | 0.673 |
| macro-F1 | 0.629 | 0.648 |
| false-MET rate | 8.3% | 8.3% |
| UNCERTAIN recall | 0.522 | 0.522 |
| predicted UNCERTAIN share | 25.5% | 22.7% |
| unsupported MET | 0 | |
| JSON validity | | 99.1% |
| quote verbatim rate | | 86.7% (75 quotes) |

Evidence overlap on gold MET: 56.0% · basis accuracy on MISSING/MISSING: 88.9%
Latency: 6.154 s/req (max 11.33 s) · peak RSS 3620 MB (last process)

## Confusion (rows gold, columns final prediction)

| gold \ pred | MET | MISSING | UNCERTAIN |
|---|---|---|---|
| MET | 33 | 9 | 8 |
| MISSING | 2 | 27 | 8 |
| UNCERTAIN | 3 | 8 | 12 |

## Per class (final)

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| MET | 0.868 | 0.660 | 0.750 | 50 |
| MISSING | 0.614 | 0.730 | 0.667 | 37 |
| UNCERTAIN | 0.429 | 0.522 | 0.471 | 23 |

## Per tag accuracy (final)

| tag | n | accuracy |
|---|---|---|
| ambiguous_duration | 8 | 1.000 |
| certification | 15 | 0.600 |
| contradictory_requirement | 2 | 1.000 |
| education | 9 | 0.556 |
| equivalence | 17 | 0.706 |
| exact | 22 | 0.682 |
| experience_years | 12 | 0.250 |
| language | 7 | 0.286 |
| negation | 6 | 0.500 |
| not_documented | 18 | 1.000 |
| rag_only_term | 6 | 1.000 |
| related_not_equivalent | 21 | 0.762 |
