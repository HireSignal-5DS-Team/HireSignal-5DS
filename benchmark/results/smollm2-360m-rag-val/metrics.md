# smollm2-360m-rag-val: HuggingFaceTB/SmolLM2-360M-Instruct | knowledge=rag.bm25 | split=val

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.108 | 0.000 |
| accuracy | 0.193 | 0.000 |
| false-MET rate | 0.000 | 0.000 |
| MET P / R | 0.000 / 0.000 | 0.000 / 0.000 |
| MISSING P / R | 0.000 / 0.000 | 0.000 / 0.000 |
| UNCERTAIN P / R | 0.193 / 1.000 | 0.000 / 0.000 |

- JSON/schema validity: 0.000
- basis accuracy (final): 0.193
- raw quote validity (exact CV substring): n/a of 0 quotes
- raw MET answers with >= 1 verified quote: n/a
- evidence attribution vs gold span (correct MET/contradicted, n=0): n/a
- validator changed the decision: 1.000
- needs human review: 1.000
- latency per requirement (s): mean 9.81, p50 6.40, p95 15.96

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 1.000 |
| certification | 13 | 0.000 |
| contradictory_evidence | 31 | 0.000 |
| date_range | 8 | 0.000 |
| direct_match | 8 | 0.000 |
| distractor_details | 74 | 0.189 |
| education | 10 | 0.000 |
| equivalent_skill_alias | 21 | 0.000 |
| implicit_project_evidence | 15 | 0.000 |
| insufficient_experience | 17 | 0.000 |
| language | 14 | 0.000 |
| missing_evidence | 18 | 0.000 |
| multi_requirement | 117 | 0.197 |
| negation_trap | 22 | 0.000 |
| partial_evidence | 18 | 1.000 |
| rag_suggests_absent_skill | 11 | 0.000 |
| sufficient_experience | 25 | 0.000 |

Peak RSS: 2792.1 MB; model load: 5.48 s
