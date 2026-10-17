**Job Agent evaluation** (2026-10-17, 10 real offers, 104 gold requirements, model `hf.co/numind/NuExtract-2.0-2B-GGUF:Q4_K_M`, mode `inline`, repeat 2)

| Measure | `job-v1` | `job-v2` |
|---|---|---|
| Precision (kept requirements that are correct) | 0.267 | 0.184 |
| Recall (gold requirements found) | 0.192 | 0.154 |
| F1 | 0.223 | 0.168 |
| Correct / extra / missed | 20 / 55 / 84 | 16 / 71 / 88 |
| kind accuracy (on matched) | 0.95 | 1.0 |
| category accuracy (on matched) | 0.65 | 0.375 |
| min_years accuracy (on matched) | 1.0 | 0.938 |
| Invented quotes dropped by guardrails | 24 | 2 |
| Cards flagged for human review | 2 | 1 |
| Offers with no valid card | 2 | 3 |
| Mean latency per offer (s) | 45.8 | 59.6 |
| Stable across repeats | 9/10 | 7/10 |

Per offer (F1):

| Offer | gold | `job-v1` | `job-v2` |
|---|---|---|---|
| usajobs-883161100 | 12 | 0.0 | 0.0 |
| usajobs-883337000 | 16 | 0.214 | 0.0 |
| usajobs-883386100 | 6 | 0.286 | 0.0 |
| usajobs-883511200 | 8 | 0.7 | 0.522 |
| usajobs-883699600 | 29 | 0.36 | 0.25 |
| usajobs-883827900 | 3 | 0.0 | 0.16 |
| usajobs-884301900 | 10 | 0.0 | 0.0 |
| usajobs-884783000 | 6 | 0.0 | 0.182 |
| usajobs-885947600 | 12 | 0.0 | 0.0 |
| usajobs-886071700 | 2 | 0.0 | 0.4 |
