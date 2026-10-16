# Validator replay of the E2E arms (validator v1 (eae4286); saved LIVE raw outputs, no model call)

## base

| arm | n | macro-F1 | false-MET | review rate | decisions changed vs saved | refs rebuilt != saved |
|---|---|---|---|---|---|---|
| bm25 | 202 | 0.590 | 0.009 | 0.777 | 0 | 0 |
| gated | 202 | 0.599 | 0.009 | 0.767 | 0 | 0 |
| none | 202 | 0.614 | 0.009 | 0.802 | 0 | 0 |

| comparison | Δ macro-F1 | 95% CI | base-only / cand-only correct | McNemar p |
|---|---|---|---|---|
| bm25 vs none | -0.024 | [-0.061, +0.010] | 11 / 6 | 0.332 |
| gated vs none | -0.014 | [-0.038, +0.008] | 5 / 2 | 0.453 |
| gated vs bm25 | +0.009 | [-0.026, +0.045] | 7 / 9 | 0.804 |

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

