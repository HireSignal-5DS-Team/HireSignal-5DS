# qwen3-0.6b-rag-val: Qwen/Qwen3-0.6B | knowledge=rag.bm25 | split=val

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.222 | 0.122 |
| accuracy | 0.262 | 0.084 |
| false-MET rate | 0.000 | 0.000 |
| MET P / R | 0.000 / 0.000 | 0.000 / 0.000 |
| MISSING P / R | 0.842 / 0.208 | 0.842 / 0.208 |
| UNCERTAIN P / R | 0.202 / 0.949 | 0.045 / 0.026 |

- JSON/schema validity: 0.203
- basis accuracy (final): 0.203
- raw quote validity (exact CV substring): n/a of 0 quotes
- raw MET answers with >= 1 verified quote: n/a
- evidence attribution vs gold span (correct MET/contradicted, n=12): 0.000
- validator changed the decision: 0.797
- needs human review: 0.980
- latency per requirement (s): mean 10.49, p50 10.23, p95 15.28

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 0.905 |
| certification | 13 | 0.385 |
| contradictory_evidence | 31 | 0.355 |
| date_range | 8 | 0.000 |
| direct_match | 8 | 0.000 |
| distractor_details | 74 | 0.284 |
| education | 10 | 0.300 |
| equivalent_skill_alias | 21 | 0.000 |
| implicit_project_evidence | 15 | 0.000 |
| insufficient_experience | 17 | 0.059 |
| language | 14 | 0.000 |
| missing_evidence | 18 | 0.222 |
| multi_requirement | 117 | 0.256 |
| negation_trap | 22 | 0.409 |
| partial_evidence | 18 | 1.000 |
| rag_suggests_absent_skill | 11 | 0.000 |
| sufficient_experience | 25 | 0.000 |

Peak RSS: 5099.3 MB; model load: 6.78 s
