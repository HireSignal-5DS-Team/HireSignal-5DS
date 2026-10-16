# base__gated: Qwen/Qwen3-4B-Instruct-2507 | knowledge=rag.gated.v1+bm25 | split=val

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.599 | 0.616 |
| accuracy | 0.594 | 0.589 |
| false-MET rate | 0.009 | 0.026 |
| MET P / R | 0.979 / 0.547 | 0.940 / 0.547 |
| MISSING P / R | 0.848 / 0.506 | 0.848 / 0.506 |
| UNCERTAIN P / R | 0.315 / 0.872 | 0.379 / 0.846 |

- JSON/schema validity: 0.906
- basis accuracy (final): 0.525
- raw quote validity (exact CV substring): 1.000 of 131 quotes
- raw MET answers with >= 1 verified quote: 1.000
- evidence attribution vs gold span (correct MET/contradicted, n=78): 0.821
- validator changed the decision: 0.104
- needs human review: 0.767
- latency per requirement (s): mean 17.30, p50 16.64, p95 23.54

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 0.762 |
| certification | 13 | 0.462 |
| contradictory_evidence | 31 | 0.742 |
| date_range | 8 | 0.125 |
| direct_match | 8 | 0.625 |
| distractor_details | 74 | 0.527 |
| education | 10 | 0.900 |
| equivalent_skill_alias | 21 | 0.381 |
| implicit_project_evidence | 15 | 0.333 |
| insufficient_experience | 17 | 0.471 |
| language | 14 | 0.857 |
| missing_evidence | 18 | 0.389 |
| multi_requirement | 117 | 0.590 |
| negation_trap | 22 | 0.682 |
| partial_evidence | 18 | 1.000 |
| rag_suggests_absent_skill | 11 | 0.091 |
| sufficient_experience | 25 | 0.560 |

Peak RSS: 547.5 MB; model load: 2.49 s
