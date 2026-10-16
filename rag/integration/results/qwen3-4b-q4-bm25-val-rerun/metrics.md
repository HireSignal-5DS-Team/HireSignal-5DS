# qwen3-4b-q4-bm25-val-rerun: Qwen/Qwen3-4B-Instruct-2507 | knowledge=rag.bm25 | split=val

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.608 | 0.639 |
| accuracy | 0.604 | 0.599 |
| false-MET rate | 0.009 | 0.017 |
| MET P / R | 0.977 / 0.500 | 0.956 / 0.500 |
| MISSING P / R | 0.833 / 0.584 | 0.833 / 0.584 |
| UNCERTAIN P / R | 0.327 / 0.872 | 0.434 / 0.846 |

- JSON/schema validity: 0.866
- basis accuracy (final): 0.520
- raw quote validity (exact CV substring): 1.000 of 121 quotes
- raw MET answers with >= 1 verified quote: 1.000
- evidence attribution vs gold span (correct MET/contradicted, n=78): 0.769
- validator changed the decision: 0.139
- needs human review: 0.767
- latency per requirement (s): mean 13.55, p50 13.15, p95 18.32

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 0.762 |
| certification | 13 | 0.231 |
| contradictory_evidence | 31 | 0.742 |
| date_range | 8 | 0.125 |
| direct_match | 8 | 0.625 |
| distractor_details | 74 | 0.595 |
| education | 10 | 0.800 |
| equivalent_skill_alias | 21 | 0.429 |
| implicit_project_evidence | 15 | 0.267 |
| insufficient_experience | 17 | 0.706 |
| language | 14 | 0.929 |
| missing_evidence | 18 | 0.333 |
| multi_requirement | 117 | 0.598 |
| negation_trap | 22 | 0.682 |
| partial_evidence | 18 | 1.000 |
| rag_suggests_absent_skill | 11 | 0.364 |
| sufficient_experience | 25 | 0.520 |

Peak RSS: 535.2 MB; model load: 3.09 s
