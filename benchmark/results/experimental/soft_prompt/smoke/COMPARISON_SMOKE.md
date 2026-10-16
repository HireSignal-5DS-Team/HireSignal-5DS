# Soft prompt experiment, 4-arm comparison (SMOKE)

Backend: transformers, float32 on cpu, greedy, max 48 new tokens; 20 paired val requirements.

| arm | label | macro-F1 | Δ vs base [95 % CI] | McNemar p | false-MET | JSON valid | UNCERTAIN | p50 s | p95 s | peak RSS MB | peak VRAM MB | config |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | SMOKE | 0.061 | ref | ref | 0.000 | 0.000 | 1.000 | 0.09 | 0.10 | 962 | n/a | `7a42698dd4e7` |
| lora | SMOKE | 0.061 | +0.000 [+0.000, +0.000] | 1.000 | 0.000 | 0.000 | 1.000 | 0.11 | 0.12 | 962 | n/a | `b214560de36d` |
| soft_prompt | SMOKE | 0.061 | +0.000 [+0.000, +0.000] | 1.000 | 0.000 | 0.000 | 1.000 | 0.09 | 0.11 | 962 | n/a | `fea7a31c27db` |
| lora_soft_prompt | SMOKE | 0.061 | +0.000 [+0.000, +0.000] | 1.000 | 0.000 | 0.000 | 1.000 | 0.09 | 0.13 | 962 | n/a | `97e190582176` |

**SMOKE: tiny random model. These numbers check the plumbing only and say nothing about the Matcher.**
