# qwen3-4b-q4-none-val-rerun: Qwen/Qwen3-4B-Instruct-2507 | knowledge=none | split=val

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.649 | 0.662 |
| accuracy | 0.649 | 0.644 |
| false-MET rate | 0.009 | 0.017 |
| MET P / R | 0.980 / 0.558 | 0.960 / 0.558 |
| MISSING P / R | 0.860 / 0.636 | 0.860 / 0.636 |
| UNCERTAIN P / R | 0.354 / 0.872 | 0.407 / 0.846 |

- JSON/schema validity: 0.931
- basis accuracy (final): 0.559
- raw quote validity (exact CV substring): 1.000 of 128 quotes
- raw MET answers with >= 1 verified quote: 1.000
- evidence attribution vs gold span (correct MET/contradicted, n=84): 0.786
- validator changed the decision: 0.074
- needs human review: 0.792
- latency per requirement (s): mean 11.10, p50 10.58, p95 15.43

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 0.762 |
| certification | 13 | 0.538 |
| contradictory_evidence | 31 | 0.806 |
| date_range | 8 | 0.125 |
| direct_match | 8 | 0.625 |
| distractor_details | 74 | 0.622 |
| education | 10 | 0.900 |
| equivalent_skill_alias | 21 | 0.286 |
| implicit_project_evidence | 15 | 0.400 |
| insufficient_experience | 17 | 0.647 |
| language | 14 | 1.000 |
| missing_evidence | 18 | 0.444 |
| multi_requirement | 117 | 0.667 |
| negation_trap | 22 | 0.727 |
| partial_evidence | 18 | 1.000 |
| rag_suggests_absent_skill | 11 | 0.455 |
| sufficient_experience | 25 | 0.600 |

Peak RSS: 520.2 MB; model load: 2.36 s
