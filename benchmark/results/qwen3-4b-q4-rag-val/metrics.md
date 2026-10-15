# qwen3-4b-q4-rag-val: Qwen/Qwen3-4B-Instruct-2507 | knowledge=rag.bm25 | split=val

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.630 | 0.647 |
| accuracy | 0.629 | 0.624 |
| false-MET rate | 0.009 | 0.026 |
| MET P / R | 0.981 / 0.605 | 0.945 / 0.605 |
| MISSING P / R | 0.851 / 0.519 | 0.851 / 0.519 |
| UNCERTAIN P / R | 0.343 / 0.897 | 0.410 / 0.872 |

- JSON/schema validity: 0.916
- basis accuracy (final): 0.574
- raw quote validity (exact CV substring): 1.000 of 141 quotes
- raw MET answers with >= 1 verified quote: 1.000
- evidence attribution vs gold span (correct MET/contradicted, n=83): 0.855
- validator changed the decision: 0.094
- needs human review: 0.743
- latency per requirement (s): mean 22.21, p50 16.35, p95 34.28

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 0.810 |
| certification | 13 | 0.231 |
| contradictory_evidence | 31 | 0.710 |
| date_range | 8 | 0.125 |
| direct_match | 8 | 0.625 |
| distractor_details | 74 | 0.608 |
| education | 10 | 0.900 |
| equivalent_skill_alias | 21 | 0.571 |
| implicit_project_evidence | 15 | 0.400 |
| insufficient_experience | 17 | 0.529 |
| language | 14 | 0.929 |
| missing_evidence | 18 | 0.278 |
| multi_requirement | 117 | 0.607 |
| negation_trap | 22 | 0.636 |
| partial_evidence | 18 | 1.000 |
| rag_suggests_absent_skill | 11 | 0.364 |
| sufficient_experience | 25 | 0.600 |

Peak RSS: 514.4 MB; model load: 8.35 s
