# base__none: Qwen/Qwen3-4B-Instruct-2507 | knowledge=none | split=val

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.614 | 0.627 |
| accuracy | 0.609 | 0.604 |
| false-MET rate | 0.009 | 0.026 |
| MET P / R | 0.979 / 0.535 | 0.939 / 0.535 |
| MISSING P / R | 0.860 / 0.558 | 0.860 / 0.558 |
| UNCERTAIN P / R | 0.324 / 0.872 | 0.379 / 0.846 |

- JSON/schema validity: 0.921
- basis accuracy (final): 0.540
- raw quote validity (exact CV substring): 1.000 of 129 quotes
- raw MET answers with >= 1 verified quote: 1.000
- evidence attribution vs gold span (correct MET/contradicted, n=77): 0.818
- validator changed the decision: 0.089
- needs human review: 0.802
- latency per requirement (s): mean 17.06, p50 16.10, p95 23.10

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 0.762 |
| certification | 13 | 0.462 |
| contradictory_evidence | 31 | 0.742 |
| date_range | 8 | 0.125 |
| direct_match | 8 | 0.625 |
| distractor_details | 74 | 0.568 |
| education | 10 | 0.900 |
| equivalent_skill_alias | 21 | 0.286 |
| implicit_project_evidence | 15 | 0.333 |
| insufficient_experience | 17 | 0.471 |
| language | 14 | 0.857 |
| missing_evidence | 18 | 0.389 |
| multi_requirement | 117 | 0.624 |
| negation_trap | 22 | 0.682 |
| partial_evidence | 18 | 1.000 |
| rag_suggests_absent_skill | 11 | 0.455 |
| sufficient_experience | 25 | 0.600 |

Peak RSS: 523.8 MB; model load: 2.35 s
