# qwen3-4b-q4+hslora-rag-val: Qwen/Qwen3-4B-Instruct-2507+lora | knowledge=rag.bm25 | split=val

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.897 | 0.903 |
| accuracy | 0.921 | 0.921 |
| false-MET rate | 0.034 | 0.060 |
| MET P / R | 0.955 / 0.977 | 0.923 / 0.977 |
| MISSING P / R | 0.892 / 0.961 | 0.892 / 0.961 |
| UNCERTAIN P / R | 0.903 / 0.718 | 1.000 / 0.718 |

- JSON/schema validity: 1.000
- basis accuracy (final): 0.916
- raw quote validity (exact CV substring): 1.000 of 146 quotes
- raw MET answers with >= 1 verified quote: 1.000
- evidence attribution vs gold span (correct MET/contradicted, n=129): 1.000
- validator changed the decision: 0.015
- needs human review: 0.574
- latency per requirement (s): mean 13.41, p50 13.09, p95 21.46

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 0.714 |
| certification | 13 | 1.000 |
| contradictory_evidence | 31 | 1.000 |
| date_range | 8 | 0.875 |
| direct_match | 8 | 1.000 |
| distractor_details | 74 | 0.892 |
| education | 10 | 1.000 |
| equivalent_skill_alias | 21 | 0.952 |
| implicit_project_evidence | 15 | 1.000 |
| insufficient_experience | 17 | 0.824 |
| language | 14 | 1.000 |
| missing_evidence | 18 | 1.000 |
| multi_requirement | 117 | 0.906 |
| negation_trap | 22 | 1.000 |
| partial_evidence | 18 | 0.722 |
| rag_suggests_absent_skill | 11 | 1.000 |
| sufficient_experience | 25 | 0.960 |

Peak RSS: 524.1 MB; model load: 3.53 s
