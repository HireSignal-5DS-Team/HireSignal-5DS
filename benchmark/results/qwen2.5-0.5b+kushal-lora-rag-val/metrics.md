# qwen2.5-0.5b+kushal-lora-rag-val: Qwen/Qwen2.5-0.5B-Instruct + Kus-hal/resume-screener-lora | knowledge=rag.bm25 | split=val

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.116 | 0.008 |
| accuracy | 0.193 | 0.005 |
| false-MET rate | 0.000 | 0.000 |
| MET P / R | 0.000 / 0.000 | 0.000 / 0.000 |
| MISSING P / R | 0.167 / 0.013 | 0.167 / 0.013 |
| UNCERTAIN P / R | 0.194 / 0.974 | 0.000 / 0.000 |

- JSON/schema validity: 0.030
- basis accuracy (final): 0.193
- raw quote validity (exact CV substring): 0.889 of 9 quotes
- raw MET answers with >= 1 verified quote: n/a
- evidence attribution vs gold span (correct MET/contradicted, n=1): 0.000
- validator changed the decision: 0.970
- needs human review: 0.995
- latency per requirement (s): mean 11.75, p50 9.41, p95 19.72

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 0.952 |
| certification | 13 | 0.000 |
| contradictory_evidence | 31 | 0.000 |
| date_range | 8 | 0.000 |
| direct_match | 8 | 0.000 |
| distractor_details | 74 | 0.176 |
| education | 10 | 0.000 |
| equivalent_skill_alias | 21 | 0.000 |
| implicit_project_evidence | 15 | 0.000 |
| insufficient_experience | 17 | 0.059 |
| language | 14 | 0.000 |
| missing_evidence | 18 | 0.000 |
| multi_requirement | 117 | 0.197 |
| negation_trap | 22 | 0.000 |
| partial_evidence | 18 | 1.000 |
| rag_suggests_absent_skill | 11 | 0.000 |
| sufficient_experience | 25 | 0.000 |

Peak RSS: 3617.4 MB; model load: 8.02 s
