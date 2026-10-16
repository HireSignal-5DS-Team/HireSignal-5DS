# lora__gated: Qwen/Qwen3-4B-Instruct-2507+lora | knowledge=rag.gated.v1+bm25 | split=val

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.903 | 0.914 |
| accuracy | 0.921 | 0.921 |
| false-MET rate | 0.026 | 0.069 |
| MET P / R | 0.965 / 0.965 | 0.912 / 0.965 |
| MISSING P / R | 0.900 / 0.935 | 0.900 / 0.935 |
| UNCERTAIN P / R | 0.861 / 0.795 | 1.000 / 0.795 |

- JSON/schema validity: 1.000
- basis accuracy (final): 0.901
- raw quote validity (exact CV substring): 1.000 of 152 quotes
- raw MET answers with >= 1 verified quote: 1.000
- evidence attribution vs gold span (correct MET/contradicted, n=126): 1.000
- validator changed the decision: 0.025
- needs human review: 0.589
- latency per requirement (s): mean 14.03, p50 14.67, p95 17.25

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 0.714 |
| certification | 13 | 1.000 |
| contradictory_evidence | 31 | 1.000 |
| date_range | 8 | 0.875 |
| direct_match | 8 | 1.000 |
| distractor_details | 74 | 0.892 |
| education | 10 | 1.000 |
| equivalent_skill_alias | 21 | 0.905 |
| implicit_project_evidence | 15 | 1.000 |
| insufficient_experience | 17 | 0.706 |
| language | 14 | 1.000 |
| missing_evidence | 18 | 1.000 |
| multi_requirement | 117 | 0.889 |
| negation_trap | 22 | 1.000 |
| partial_evidence | 18 | 0.889 |
| rag_suggests_absent_skill | 11 | 1.000 |
| sufficient_experience | 25 | 0.960 |

Peak RSS: 547.5 MB; model load: 3.93 s
