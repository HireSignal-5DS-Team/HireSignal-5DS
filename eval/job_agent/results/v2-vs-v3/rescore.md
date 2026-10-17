**Job Agent evaluation** (2026-10-17, re-scored 2026-10-17, 10 real offers, 104 gold requirements, model `hf.co/numind/NuExtract-2.0-2B-GGUF:Q4_K_M`, mode `inline`, repeat 2)

**1. Requirement sentences found** (main score: did the agent find each requirement of the offer?)

| Measure | `job-v2` | `job-v3` |
|---|---|---|
| Precision | 0.394 | 0.392 |
| Recall | 0.619 | 0.69 |
| **F1** | **0.481** | **0.5** |
| Found / extra / missed | 52 / 80 / 32 | 58 / 90 / 26 |
| kind accuracy (on found) | 0.904 | 0.862 |
| category accuracy (on found) | 0.635 | 0.793 |
| min_years accuracy (on found) | 1.0 | 0.948 |

**2. Skill names** (on the sentences found: are the skill_terms right?)

| Measure | `job-v2` | `job-v3` |
|---|---|---|
| Precision | 0.484 | 1.0 |
| Recall | 0.205 | 0.039 |
| **F1** | **0.288** | **0.075** |
| Right / wrong / missing | 15 / 16 / 58 | 3 / 0 / 74 |

**3. Strict** (full requirement: right sentence AND a shared skill name)

| Measure | `job-v2` | `job-v3` |
|---|---|---|
| F1 | 0.227 | 0.165 |
| Correct / extra / missed | 27 / 107 / 77 | 21 / 130 / 83 |

**Other**

| Measure | `job-v2` | `job-v3` |
|---|---|---|
| Invented quotes dropped by guardrails | 0 | 10 |
| Offers with no valid card | 0 | 0 |
| Mean latency per offer (s) | 52.3 | 43.1 |
| Stable across repeats | 3/10 | 10/10 |

Per offer (sentences F1 / skills F1):

| Offer | sentences | `job-v2` | `job-v3` |
|---|---|---|---|
| usajobs-883161100 | 6 | 0.75 / 0.0 | 0.476 / 0.0 |
| usajobs-883337000 | 16 | 0.621 / 0.0 | 0.462 / 0.0 |
| usajobs-883386100 | 5 | 0.222 / 0.0 | 0.211 / 0.0 |
| usajobs-883511200 | 6 | 0.4 / 0.615 | 0.387 / 0.0 |
| usajobs-883699600 | 18 | 0.973 / 0.333 | 0.973 / 0.167 |
| usajobs-883827900 | 3 | 0.16 / 0.0 | 0.267 / 0.0 |
| usajobs-884301900 | 10 | 0.696 / 0.4 | 0.64 / 0.0 |
| usajobs-884783000 | 6 | 0.182 / 0.0 | 0.667 / 0.0 |
| usajobs-885947600 | 12 | 0.0 / 0.0 | 0.316 / 0.0 |
| usajobs-886071700 | 2 | 0.267 / 0.0 | 0.19 / 0.0 |
