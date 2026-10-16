# lora__none-repeat: Qwen/Qwen3-4B-Instruct-2507+lora | knowledge=none | split=val

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.905 | 0.916 |
| accuracy | 0.916 | 0.916 |
| false-MET rate | 0.026 | 0.069 |
| MET P / R | 0.964 / 0.930 | 0.909 / 0.930 |
| MISSING P / R | 0.889 / 0.935 | 0.889 / 0.935 |
| UNCERTAIN P / R | 0.868 / 0.846 | 1.000 / 0.846 |

- JSON/schema validity: 1.000
- basis accuracy (final): 0.906
- raw quote validity (exact CV substring): 1.000 of 140 quotes
- raw MET answers with >= 1 verified quote: 1.000
- evidence attribution vs gold span (correct MET/contradicted, n=123): 1.000
- validator changed the decision: 0.025
- needs human review: 0.658
- latency per requirement (s): mean 13.75, p50 14.26, p95 17.50

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 0.810 |
| certification | 13 | 1.000 |
| contradictory_evidence | 31 | 1.000 |
| date_range | 8 | 0.875 |
| direct_match | 8 | 1.000 |
| distractor_details | 74 | 0.878 |
| education | 10 | 1.000 |
| equivalent_skill_alias | 21 | 0.762 |
| implicit_project_evidence | 15 | 1.000 |
| insufficient_experience | 17 | 0.706 |
| language | 14 | 1.000 |
| missing_evidence | 18 | 1.000 |
| multi_requirement | 117 | 0.889 |
| negation_trap | 22 | 1.000 |
| partial_evidence | 18 | 0.889 |
| rag_suggests_absent_skill | 11 | 1.000 |
| sufficient_experience | 25 | 0.960 |

Peak RSS: 523.5 MB; model load: 2.42 s
