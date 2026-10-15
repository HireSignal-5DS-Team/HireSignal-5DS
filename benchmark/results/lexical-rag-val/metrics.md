# lexical-rag-val: lexical_baseline | knowledge=rag.bm25 | split=val

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.436 | 0.436 |
| accuracy | 0.584 | 0.584 |
| false-MET rate | 0.560 | 0.560 |
| MET P / R | 0.508 / 0.779 | 0.508 / 0.779 |
| MISSING P / R | 0.729 / 0.662 | 0.729 / 0.662 |
| UNCERTAIN P / R | 0.000 / 0.000 | 0.000 / 0.000 |

- JSON/schema validity: 1.000
- basis accuracy (final): 0.559
- raw quote validity (exact CV substring): 1.000 of 149 quotes
- raw MET answers with >= 1 verified quote: 1.000
- evidence attribution vs gold span (correct MET/contradicted, n=89): 0.944
- validator changed the decision: 0.000
- needs human review: 0.381
- latency per requirement (s): mean 0.00, p50 0.00, p95 0.00

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 0.000 |
| certification | 13 | 0.308 |
| contradictory_evidence | 31 | 0.161 |
| date_range | 8 | 1.000 |
| direct_match | 8 | 1.000 |
| distractor_details | 74 | 0.608 |
| education | 10 | 1.000 |
| equivalent_skill_alias | 21 | 0.810 |
| implicit_project_evidence | 15 | 0.000 |
| insufficient_experience | 17 | 1.000 |
| language | 14 | 0.714 |
| missing_evidence | 18 | 1.000 |
| multi_requirement | 117 | 0.607 |
| negation_trap | 22 | 0.000 |
| partial_evidence | 18 | 0.000 |
| rag_suggests_absent_skill | 11 | 1.000 |
| sufficient_experience | 25 | 1.000 |

Peak RSS: 522.1 MB; model load: 2.62 s
