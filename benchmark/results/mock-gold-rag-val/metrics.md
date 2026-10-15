# MOCK mock-gold-rag-val: mock | knowledge=rag.bm25 | split=val

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 1.000 | 1.000 |
| accuracy | 1.000 | 1.000 |
| false-MET rate | 0.000 | 0.000 |
| MET P / R | 1.000 / 1.000 | 1.000 / 1.000 |
| MISSING P / R | 1.000 / 1.000 | 1.000 / 1.000 |
| UNCERTAIN P / R | 1.000 / 1.000 | 1.000 / 1.000 |

- JSON/schema validity: 1.000
- basis accuracy (final): 1.000
- raw quote validity (exact CV substring): 1.000 of 134 quotes
- raw MET answers with >= 1 verified quote: 1.000
- evidence attribution vs gold span (correct MET/contradicted, n=134): 1.000
- validator changed the decision: 0.000
- needs human review: 0.584
- latency per requirement (s): mean 0.00, p50 0.00, p95 0.00

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 1.000 |
| certification | 13 | 1.000 |
| contradictory_evidence | 31 | 1.000 |
| date_range | 8 | 1.000 |
| direct_match | 8 | 1.000 |
| distractor_details | 74 | 1.000 |
| education | 10 | 1.000 |
| equivalent_skill_alias | 21 | 1.000 |
| implicit_project_evidence | 15 | 1.000 |
| insufficient_experience | 17 | 1.000 |
| language | 14 | 1.000 |
| missing_evidence | 18 | 1.000 |
| multi_requirement | 117 | 1.000 |
| negation_trap | 22 | 1.000 |
| partial_evidence | 18 | 1.000 |
| rag_suggests_absent_skill | 11 | 1.000 |
| sufficient_experience | 25 | 1.000 |

Peak RSS: 521.9 MB; model load: 2.78 s
