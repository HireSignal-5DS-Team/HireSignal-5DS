# qwen3-4b-q4-dense-val: Qwen/Qwen3-4B-Instruct-2507 | knowledge=rag.dense.e5-small | split=val

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.599 | 0.631 |
| accuracy | 0.594 | 0.594 |
| false-MET rate | 0.009 | 0.026 |
| MET P / R | 0.977 / 0.500 | 0.935 / 0.500 |
| MISSING P / R | 0.830 / 0.571 | 0.830 / 0.571 |
| UNCERTAIN P / R | 0.314 / 0.846 | 0.423 / 0.846 |

- JSON/schema validity: 0.876
- basis accuracy (final): 0.500
- raw quote validity (exact CV substring): 1.000 of 123 quotes
- raw MET answers with >= 1 verified quote: 1.000
- evidence attribution vs gold span (correct MET/contradicted, n=80): 0.750
- validator changed the decision: 0.134
- needs human review: 0.777
- latency per requirement (s): mean 16.81, p50 16.41, p95 23.45

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 0.714 |
| certification | 13 | 0.385 |
| contradictory_evidence | 31 | 0.806 |
| date_range | 8 | 0.125 |
| direct_match | 8 | 0.375 |
| distractor_details | 74 | 0.554 |
| education | 10 | 0.800 |
| equivalent_skill_alias | 21 | 0.429 |
| implicit_project_evidence | 15 | 0.400 |
| insufficient_experience | 17 | 0.706 |
| language | 14 | 0.857 |
| missing_evidence | 18 | 0.333 |
| multi_requirement | 117 | 0.564 |
| negation_trap | 22 | 0.773 |
| partial_evidence | 18 | 1.000 |
| rag_suggests_absent_skill | 11 | 0.091 |
| sufficient_experience | 25 | 0.560 |

Peak RSS: 1439.4 MB; model load: 0.01 s
