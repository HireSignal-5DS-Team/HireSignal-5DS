# qwen3-4b-q4-none-val: Qwen/Qwen3-4B-Instruct-2507 | knowledge=none | split=val

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.634 | 0.641 |
| accuracy | 0.634 | 0.629 |
| false-MET rate | 0.009 | 0.026 |
| MET P / R | 0.981 / 0.616 | 0.946 / 0.616 |
| MISSING P / R | 0.854 / 0.532 | 0.854 / 0.532 |
| UNCERTAIN P / R | 0.340 / 0.872 | 0.375 / 0.846 |

- JSON/schema validity: 0.950
- basis accuracy (final): 0.574
- raw quote validity (exact CV substring): 1.000 of 139 quotes
- raw MET answers with >= 1 verified quote: 1.000
- evidence attribution vs gold span (correct MET/contradicted, n=84): 0.857
- validator changed the decision: 0.059
- needs human review: 0.782
- latency per requirement (s): mean 13.93, p50 12.94, p95 20.75

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 0.762 |
| certification | 13 | 0.385 |
| contradictory_evidence | 31 | 0.710 |
| date_range | 8 | 0.125 |
| direct_match | 8 | 0.625 |
| distractor_details | 74 | 0.581 |
| education | 10 | 1.000 |
| equivalent_skill_alias | 21 | 0.286 |
| implicit_project_evidence | 15 | 0.600 |
| insufficient_experience | 17 | 0.529 |
| language | 14 | 0.929 |
| missing_evidence | 18 | 0.278 |
| multi_requirement | 117 | 0.624 |
| negation_trap | 22 | 0.636 |
| partial_evidence | 18 | 1.000 |
| rag_suggests_absent_skill | 11 | 0.455 |
| sufficient_experience | 25 | 0.640 |

Peak RSS: 517.4 MB; model load: 2.66 s
