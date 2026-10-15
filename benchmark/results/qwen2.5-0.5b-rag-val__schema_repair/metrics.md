# qwen2.5-0.5b-rag-val__schema_repair (post-hoc adapter `schema_repair`, no new inference)

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.265 | 0.386 |
| accuracy | 0.307 | 0.446 |
| false-MET rate | 0.009 | 0.345 |
| MET P / R | 0.800 / 0.047 | 0.518 / 0.500 |
| MISSING P / R | 0.404 / 0.545 | 0.404 / 0.545 |
| UNCERTAIN P / R | 0.172 / 0.410 | 0.333 / 0.128 |

- JSON/schema validity: 1.000
- basis accuracy (final): 0.188
- raw quote validity (exact CV substring): 0.067 of 150 quotes
- raw MET answers with >= 1 verified quote: 0.072
- evidence attribution vs gold span (correct MET/contradicted, n=28): 0.071
- validator changed the decision: 0.386
- needs human review: 0.827
- latency per requirement (s): mean 7.13, p50 5.97, p95 12.50

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 0.476 |
| certification | 13 | 0.462 |
| contradictory_evidence | 31 | 0.516 |
| date_range | 8 | 0.125 |
| direct_match | 8 | 0.000 |
| distractor_details | 74 | 0.324 |
| education | 10 | 0.500 |
| equivalent_skill_alias | 21 | 0.000 |
| implicit_project_evidence | 15 | 0.133 |
| insufficient_experience | 17 | 0.471 |
| language | 14 | 0.000 |
| missing_evidence | 18 | 0.778 |
| multi_requirement | 117 | 0.308 |
| negation_trap | 22 | 0.636 |
| partial_evidence | 18 | 0.333 |
| rag_suggests_absent_skill | 11 | 0.364 |
| sufficient_experience | 25 | 0.040 |
