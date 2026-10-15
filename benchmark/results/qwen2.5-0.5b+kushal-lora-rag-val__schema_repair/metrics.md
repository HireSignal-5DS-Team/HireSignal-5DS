# qwen2.5-0.5b+kushal-lora-rag-val__schema_repair (post-hoc adapter `schema_repair`, no new inference)

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.245 | 0.226 |
| accuracy | 0.292 | 0.262 |
| false-MET rate | 0.000 | 0.000 |
| MET P / R | 0.000 / 0.000 | 0.000 / 0.000 |
| MISSING P / R | 0.411 / 0.481 | 0.411 / 0.481 |
| UNCERTAIN P / R | 0.196 / 0.564 | 0.165 / 0.410 |

- JSON/schema validity: 0.926
- basis accuracy (final): 0.198
- raw quote validity (exact CV substring): 0.543 of 199 quotes
- raw MET answers with >= 1 verified quote: n/a
- evidence attribution vs gold span (correct MET/contradicted, n=22): 0.227
- validator changed the decision: 0.074
- needs human review: 0.946
- latency per requirement (s): mean 11.75, p50 9.41, p95 19.72

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 0.571 |
| certification | 13 | 0.308 |
| contradictory_evidence | 31 | 0.452 |
| date_range | 8 | 0.000 |
| direct_match | 8 | 0.000 |
| distractor_details | 74 | 0.365 |
| education | 10 | 0.300 |
| equivalent_skill_alias | 21 | 0.000 |
| implicit_project_evidence | 15 | 0.000 |
| insufficient_experience | 17 | 0.471 |
| language | 14 | 0.071 |
| missing_evidence | 18 | 0.611 |
| multi_requirement | 117 | 0.359 |
| negation_trap | 22 | 0.500 |
| partial_evidence | 18 | 0.556 |
| rag_suggests_absent_skill | 11 | 0.364 |
| sufficient_experience | 25 | 0.000 |
