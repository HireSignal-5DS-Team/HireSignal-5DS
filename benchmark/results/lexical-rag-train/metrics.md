# lexical-rag-train: lexical_baseline | knowledge=rag.bm25 | split=train

Requirements evaluated: 681

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.432 | 0.432 |
| accuracy | 0.598 | 0.598 |
| false-MET rate | 0.572 | 0.572 |
| MET P / R | 0.534 / 0.807 | 0.534 / 0.807 |
| MISSING P / R | 0.732 / 0.590 | 0.732 / 0.590 |
| UNCERTAIN P / R | 0.000 / 0.000 | 0.000 / 0.000 |

- JSON/schema validity: 1.000
- basis accuracy (final): 0.586
- raw quote validity (exact CV substring): 1.000 of 507 quotes
- raw MET answers with >= 1 verified quote: 1.000
- evidence attribution vs gold span (correct MET/contradicted, n=300): 0.963
- validator changed the decision: 0.000
- needs human review: 0.323
- latency per requirement (s): mean 0.00, p50 0.00, p95 0.00

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 53 | 0.000 |
| certification | 47 | 0.447 |
| contradictory_evidence | 119 | 0.067 |
| date_range | 43 | 1.000 |
| direct_match | 54 | 1.000 |
| distractor_details | 388 | 0.606 |
| education | 32 | 0.906 |
| equivalent_skill_alias | 55 | 0.745 |
| implicit_project_evidence | 46 | 0.022 |
| insufficient_experience | 47 | 0.979 |
| language | 45 | 0.400 |
| missing_evidence | 57 | 1.000 |
| multi_requirement | 410 | 0.624 |
| negation_trap | 81 | 0.000 |
| partial_evidence | 50 | 0.000 |
| rag_suggests_absent_skill | 50 | 1.000 |
| sufficient_experience | 99 | 1.000 |

Peak RSS: 524.5 MB; model load: 5.06 s
