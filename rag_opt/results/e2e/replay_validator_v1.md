# Validator replay of the E2E arms (validator v1 (current branch); saved LIVE raw outputs, no model call)

## lora

| arm | n | macro-F1 | false-MET | review rate | decisions changed vs saved | refs rebuilt != saved |
|---|---|---|---|---|---|---|
| bm25 | 202 | 0.897 | 0.035 | 0.574 | 0 | 0 |
| gated | 202 | 0.903 | 0.026 | 0.589 | 0 | 0 |
| none | 202 | 0.908 | 0.026 | 0.663 | 0 | 0 |
| none-repeat | 202 | 0.905 | 0.026 | 0.658 | 0 | 0 |

| comparison | Δ macro-F1 | 95% CI | base-only / cand-only correct | McNemar p |
|---|---|---|---|---|
| bm25 vs none | -0.011 | [-0.047, +0.021] | 4 / 4 | 1.000 |
| gated vs none | -0.005 | [-0.028, +0.014] | 2 / 2 | 1.000 |
| none-repeat vs none | -0.003 | [-0.024, +0.017] | 2 / 1 | 1.000 |
| gated vs bm25 | +0.006 | [-0.032, +0.046] | 4 / 4 | 1.000 |

