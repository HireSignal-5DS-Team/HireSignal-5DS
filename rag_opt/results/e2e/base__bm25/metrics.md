# base__bm25: Qwen/Qwen3-4B-Instruct-2507 | knowledge=rag.bm25 | split=val

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.590 | 0.616 |
| accuracy | 0.584 | 0.579 |
| false-MET rate | 0.009 | 0.017 |
| MET P / R | 0.978 / 0.523 | 0.957 / 0.523 |
| MISSING P / R | 0.830 / 0.506 | 0.830 / 0.506 |
| UNCERTAIN P / R | 0.312 / 0.872 | 0.398 / 0.846 |

- JSON/schema validity: 0.876
- basis accuracy (final): 0.520
- raw quote validity (exact CV substring): 1.000 of 127 quotes
- raw MET answers with >= 1 verified quote: 1.000
- evidence attribution vs gold span (correct MET/contradicted, n=76): 0.816
- validator changed the decision: 0.129
- needs human review: 0.777
- latency per requirement (s): mean 19.17, p50 18.75, p95 26.28

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 0.762 |
| certification | 13 | 0.154 |
| contradictory_evidence | 31 | 0.710 |
| date_range | 8 | 0.125 |
| direct_match | 8 | 0.625 |
| distractor_details | 74 | 0.568 |
| education | 10 | 0.800 |
| equivalent_skill_alias | 21 | 0.429 |
| implicit_project_evidence | 15 | 0.333 |
| insufficient_experience | 17 | 0.529 |
| language | 14 | 0.929 |
| missing_evidence | 18 | 0.278 |
| multi_requirement | 117 | 0.564 |
| negation_trap | 22 | 0.636 |
| partial_evidence | 18 | 1.000 |
| rag_suggests_absent_skill | 11 | 0.273 |
| sufficient_experience | 25 | 0.560 |

Peak RSS: 541.5 MB; model load: 2.58 s
