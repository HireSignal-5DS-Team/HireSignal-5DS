# lora__none: Qwen/Qwen3-4B-Instruct-2507+lora | knowledge=none | split=test

Requirements evaluated: 199

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.681 | 0.891 |
| accuracy | 0.709 | 0.864 |
| false-MET rate | 0.121 | 0.168 |
| MET P / R | 0.803 / 0.576 | 0.824 / 0.913 |
| MISSING P / R | 0.880 / 0.786 | 0.880 / 0.786 |
| UNCERTAIN P / R | 0.379 / 0.957 | 1.000 / 0.957 |

- JSON/schema validity: 1.000
- basis accuracy (final): 0.698
- raw quote validity (exact CV substring): 1.000 of 147 quotes
- raw MET answers with >= 1 verified quote: 1.000
- evidence attribution vs gold span (correct MET/contradicted, n=84): 1.000
- validator changed the decision: 0.181
- needs human review: 0.819
- latency per requirement (s): mean 13.61, p50 14.08, p95 17.29

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 12 | 0.917 |
| certification | 12 | 1.000 |
| contradictory_evidence | 29 | 1.000 |
| date_range | 15 | 0.000 |
| direct_match | 9 | 1.000 |
| distractor_details | 88 | 0.682 |
| education | 12 | 1.000 |
| equivalent_skill_alias | 20 | 1.000 |
| implicit_project_evidence | 12 | 1.000 |
| insufficient_experience | 7 | 0.286 |
| language | 17 | 0.529 |
| missing_evidence | 24 | 1.000 |
| multi_requirement | 123 | 0.659 |
| negation_trap | 17 | 1.000 |
| partial_evidence | 11 | 1.000 |
| rag_suggests_absent_skill | 24 | 0.458 |
| sufficient_experience | 31 | 0.000 |

Peak RSS: 525.4 MB; model load: 2.73 s
