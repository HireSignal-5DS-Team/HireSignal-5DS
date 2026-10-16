# SMOKE smoke-lora: arm=lora | /home/user/HireSignal-5DS/prompt_tuning/runs/smoke/tiny_qwen3 + /home/user/HireSignal-5DS/prompt_tuning/runs/smoke/tiny_lora (merged) | transformers float32 cpu

Requirements evaluated: 20

| metric | final (after validation) | raw model output |
|---|---|---|
| macro-F1 | 0.061 | 0.000 |
| accuracy | 0.100 | 0.000 |
| false-MET rate | 0.000 | 0.000 |
| MET P / R | 0.000 / 0.000 | 0.000 / 0.000 |
| MISSING P / R | 0.000 / 0.000 | 0.000 / 0.000 |
| UNCERTAIN P / R | 0.100 / 1.000 | 0.000 / 0.000 |

- JSON/schema validity: 0.000
- basis accuracy (final): 0.100
- raw quote validity (exact CV substring): n/a of 0 quotes
- raw MET answers with >= 1 verified quote: n/a
- evidence attribution vs gold span (correct MET/contradicted, n=0): n/a
- validator changed the decision: 1.000
- needs human review: 1.000
- latency per requirement (s): mean 0.10, p50 0.11, p95 0.12

| tag | n | accuracy (final) |
|---|---|---|
| ambiguous_duration | 1 | 1.000 |
| certification | 2 | 0.000 |
| contradictory_evidence | 2 | 0.000 |
| direct_match | 3 | 0.000 |
| distractor_details | 13 | 0.077 |
| equivalent_skill_alias | 2 | 0.000 |
| implicit_project_evidence | 1 | 0.000 |
| insufficient_experience | 1 | 0.000 |
| language | 1 | 0.000 |
| missing_evidence | 2 | 0.000 |
| multi_requirement | 6 | 0.167 |
| negation_trap | 2 | 0.000 |
| partial_evidence | 1 | 1.000 |
| rag_suggests_absent_skill | 1 | 0.000 |
| sufficient_experience | 5 | 0.000 |

Peak RSS: 962.4 MB; peak VRAM: None MB; load: 0.07 s; config hash `b214560de36de4aaddf5668fb6d7806fdee59a50898392928a8c378aa692c6ac`
