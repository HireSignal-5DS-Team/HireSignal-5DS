# lexical-none-val: lexical_baseline | knowledge=none | split=val

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.373 | 0.373 |
| accuracy | 0.500 | 0.500 |
| false-MET rate | 0.560 | 0.560 |
| MET P / R | 0.435 / 0.581 | 0.435 / 0.581 |
| MISSING P / R | 0.586 / 0.662 | 0.586 / 0.662 |
| UNCERTAIN P / R | 0.000 / 0.000 | 0.000 / 0.000 |

- JSON/schema validity: 1.000
- basis accuracy (final): 0.475
- raw quote validity (exact CV substring): 1.000 of 132 quotes
- raw MET answers with >= 1 verified quote: 1.000
- evidence attribution vs gold span (correct MET/contradicted, n=72): 0.931
- validator changed the decision: 0.000
- needs human review: 0.446
- latency per requirement (s): mean 0.00, p50 0.00, p95 0.00

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 0.000 |
| certification | 13 | 0.308 |
| contradictory_evidence | 31 | 0.161 |
| date_range | 8 | 1.000 |
| direct_match | 8 | 1.000 |
| distractor_details | 74 | 0.500 |
| education | 10 | 1.000 |
| equivalent_skill_alias | 21 | 0.000 |
| implicit_project_evidence | 15 | 0.000 |
| insufficient_experience | 17 | 1.000 |
| language | 14 | 0.714 |
| missing_evidence | 18 | 1.000 |
| multi_requirement | 117 | 0.513 |
| negation_trap | 22 | 0.000 |
| partial_evidence | 18 | 0.000 |
| rag_suggests_absent_skill | 11 | 1.000 |
| sufficient_experience | 25 | 1.000 |

Peak RSS: 516.4 MB; model load: 3.01 s
