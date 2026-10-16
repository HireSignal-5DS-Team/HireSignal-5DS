# Validator replay of the E2E arms (validator v2 (after merge 20dd327); saved LIVE raw outputs, no model call)

## base

| arm | n | macro-F1 | false-MET | review rate | decisions changed vs saved | refs rebuilt != saved |
|---|---|---|---|---|---|---|
| bm25 | 202 | 0.595 | 0.000 | 0.777 | 1 | 0 |
| gated | 202 | 0.605 | 0.000 | 0.767 | 1 | 0 |
| none | 202 | 0.619 | 0.000 | 0.802 | 1 | 0 |

| comparison | Δ macro-F1 | 95% CI | base-only / cand-only correct | McNemar p |
|---|---|---|---|---|
| bm25 vs none | -0.024 | [-0.062, +0.010] | 11 / 6 | 0.332 |
| gated vs none | -0.014 | [-0.038, +0.008] | 5 / 2 | 0.453 |
| gated vs bm25 | +0.009 | [-0.026, +0.045] | 7 / 9 | 0.804 |

## lora

| arm | n | macro-F1 | false-MET | review rate | decisions changed vs saved | refs rebuilt != saved |
|---|---|---|---|---|---|---|
| bm25 | 202 | 0.926 | 0.000 | 0.584 | 4 | 0 |
| gated | 202 | 0.924 | 0.000 | 0.594 | 3 | 0 |
| none | 202 | 0.929 | 0.000 | 0.668 | 3 | 0 |
| none-repeat | 202 | 0.925 | 0.000 | 0.663 | 3 | 0 |

| comparison | Δ macro-F1 | 95% CI | base-only / cand-only correct | McNemar p |
|---|---|---|---|---|
| bm25 vs none | -0.003 | [-0.033, +0.026] | 3 / 4 | 1.000 |
| gated vs none | -0.005 | [-0.027, +0.014] | 2 / 2 | 1.000 |
| none-repeat vs none | -0.003 | [-0.024, +0.016] | 2 / 1 | 1.000 |
| gated vs bm25 | -0.002 | [-0.035, +0.031] | 4 / 3 | 1.000 |

