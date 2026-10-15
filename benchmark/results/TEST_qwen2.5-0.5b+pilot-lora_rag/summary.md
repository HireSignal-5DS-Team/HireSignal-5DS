# Benchmark run: TEST_qwen2.5-0.5b+pilot-lora_rag

split `test` · backend `transformers` · knowledge `rag.bm25` · n = 112 requirements

| metric | final (after validation) | raw model |
|---|---|---|
| accuracy | 0.598 | 0.616 |
| macro-F1 | 0.563 | 0.581 |
| false-MET rate | 1.7% | 5.2% |
| UNCERTAIN recall | 0.450 | 0.450 |
| predicted UNCERTAIN share | 24.1% | 20.5% |
| unsupported MET | 0 | |
| JSON validity | | 100.0% |
| quote verbatim rate | | 80.3% (61 quotes) |

Evidence overlap on gold MET: 48.1% · basis accuracy on MISSING/MISSING: 72.7%
Latency: 6.211 s/req (max 27.08 s) · peak RSS 3625 MB (last process)

## Confusion (rows gold, columns final prediction)

| gold \ pred | MET | MISSING | UNCERTAIN |
|---|---|---|---|
| MET | 25 | 15 | 14 |
| MISSING | 1 | 33 | 4 |
| UNCERTAIN | 0 | 11 | 9 |

## Per class (final)

| class | precision | recall | F1 | support |
|---|---|---|---|---|
| MET | 0.962 | 0.463 | 0.625 | 54 |
| MISSING | 0.559 | 0.868 | 0.680 | 38 |
| UNCERTAIN | 0.333 | 0.450 | 0.383 | 20 |

## Per tag accuracy (final)

| tag | n | accuracy |
|---|---|---|
| ambiguous_duration | 4 | 1.000 |
| certification | 8 | 0.750 |
| contradictory_requirement | 2 | 1.000 |
| education | 10 | 0.600 |
| equivalence | 12 | 0.417 |
| exact | 26 | 0.577 |
| experience_years | 15 | 0.133 |
| language | 9 | 0.556 |
| negation | 9 | 0.778 |
| not_documented | 21 | 1.000 |
| rag_only_term | 4 | 0.250 |
| related_not_equivalent | 21 | 0.714 |
