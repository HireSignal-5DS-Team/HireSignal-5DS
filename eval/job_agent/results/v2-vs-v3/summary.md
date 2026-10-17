**Job Agent evaluation** (2026-10-17, 10 real offers, 104 gold requirements, model `hf.co/numind/NuExtract-2.0-2B-GGUF:Q4_K_M`, mode `inline`, repeat 2)

| Measure | `job-v2` | `job-v3` |
|---|---|---|
| Precision (kept requirements that are correct) | 0.201 | 0.139 |
| Recall (gold requirements found) | 0.26 | 0.202 |
| F1 | 0.227 | 0.165 |
| Correct / extra / missed | 27 / 107 / 77 | 21 / 130 / 83 |
| kind accuracy (on matched) | 0.963 | 0.905 |
| category accuracy (on matched) | 0.63 | 0.952 |
| min_years accuracy (on matched) | 0.963 | 0.905 |
| Invented quotes dropped by guardrails | 0 | 10 |
| Cards flagged for human review | 0 | 0 |
| Offers with no valid card | 0 | 0 |
| Mean latency per offer (s) | 52.3 | 43.1 |
| Stable across repeats | 3/10 | 10/10 |

Per offer (F1):

| Offer | gold | `job-v2` | `job-v3` |
|---|---|---|---|
| usajobs-883161100 | 12 | 0.273 | 0.2 |
| usajobs-883337000 | 16 | 0.067 | 0.231 |
| usajobs-883386100 | 6 | 0.2 | 0.2 |
| usajobs-883511200 | 8 | 0.357 | 0.182 |
| usajobs-883699600 | 29 | 0.25 | 0.125 |
| usajobs-883827900 | 3 | 0.16 | 0.133 |
| usajobs-884301900 | 10 | 0.522 | 0.08 |
| usajobs-884783000 | 6 | 0.182 | 0.222 |
| usajobs-885947600 | 12 | 0.0 | 0.105 |
| usajobs-886071700 | 2 | 0.267 | 0.19 |
