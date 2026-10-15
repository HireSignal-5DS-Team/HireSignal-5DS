# qwen2.5-0.5b-rag-val: Qwen/Qwen2.5-0.5B-Instruct | knowledge=rag.bm25 | split=val

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.211 | 0.265 |
| accuracy | 0.233 | 0.292 |
| false-MET rate | 0.009 | 0.276 |
| MET P / R | 0.750 / 0.035 | 0.549 / 0.453 |
| MISSING P / R | 0.351 / 0.260 | 0.351 / 0.260 |
| UNCERTAIN P / R | 0.170 / 0.615 | 0.000 / 0.000 |

- JSON/schema validity: 0.634
- basis accuracy (final): 0.178
- raw quote validity (exact CV substring): 0.056 of 126 quotes
- raw MET answers with >= 1 verified quote: 0.056
- evidence attribution vs gold span (correct MET/contradicted, n=14): 0.143
- validator changed the decision: 0.698
- needs human review: 0.921
- latency per requirement (s): mean 7.13, p50 5.97, p95 12.50

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 0.667 |
| certification | 13 | 0.000 |
| contradictory_evidence | 31 | 0.194 |
| date_range | 8 | 0.000 |
| direct_match | 8 | 0.000 |
| distractor_details | 74 | 0.243 |
| education | 10 | 0.100 |
| equivalent_skill_alias | 21 | 0.000 |
| implicit_project_evidence | 15 | 0.133 |
| insufficient_experience | 17 | 0.294 |
| language | 14 | 0.000 |
| missing_evidence | 18 | 0.500 |
| multi_requirement | 117 | 0.222 |
| negation_trap | 22 | 0.273 |
| partial_evidence | 18 | 0.556 |
| rag_suggests_absent_skill | 11 | 0.000 |
| sufficient_experience | 25 | 0.000 |

Peak RSS: 3617.5 MB; model load: 8.68 s
