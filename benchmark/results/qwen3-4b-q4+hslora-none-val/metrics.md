# qwen3-4b-q4+hslora-none-val: Qwen/Qwen3-4B-Instruct-2507+lora | knowledge=none | split=val

Requirements evaluated: 202

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.908 | 0.917 |
| accuracy | 0.921 | 0.921 |
| false-MET rate | 0.026 | 0.060 |
| MET P / R | 0.964 / 0.942 | 0.920 / 0.942 |
| MISSING P / R | 0.890 / 0.948 | 0.890 / 0.948 |
| UNCERTAIN P / R | 0.889 / 0.821 | 1.000 / 0.821 |

- JSON/schema validity: 1.000
- basis accuracy (final): 0.916
- raw quote validity (exact CV substring): 1.000 of 140 quotes
- raw MET answers with >= 1 verified quote: 1.000
- evidence attribution vs gold span (correct MET/contradicted, n=125): 1.000
- validator changed the decision: 0.020
- needs human review: 0.663
- latency per requirement (s): mean 9.02, p50 8.87, p95 13.90

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 21 | 0.762 |
| certification | 13 | 1.000 |
| contradictory_evidence | 31 | 1.000 |
| date_range | 8 | 0.875 |
| direct_match | 8 | 1.000 |
| distractor_details | 74 | 0.892 |
| education | 10 | 1.000 |
| equivalent_skill_alias | 21 | 0.810 |
| implicit_project_evidence | 15 | 1.000 |
| insufficient_experience | 17 | 0.765 |
| language | 14 | 1.000 |
| missing_evidence | 18 | 1.000 |
| multi_requirement | 117 | 0.897 |
| negation_trap | 22 | 1.000 |
| partial_evidence | 18 | 0.889 |
| rag_suggests_absent_skill | 11 | 1.000 |
| sufficient_experience | 25 | 0.960 |

Peak RSS: 519.9 MB; model load: 2.33 s
