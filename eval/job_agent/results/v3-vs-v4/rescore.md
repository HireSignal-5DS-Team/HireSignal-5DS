**Job Agent evaluation** (2026-10-17, re-scored 2026-10-17, 10 real offers, 104 gold requirements, model `hf.co/numind/NuExtract-2.0-2B-GGUF:Q4_K_M`, mode `inline`, repeat 2)

**1. Requirement sentences found** (main score: did the agent find each requirement of the offer?)

| Measure | `job-v3` | `job-v4` |
|---|---|---|
| Precision | 0.393 | 0.405 |
| Recall | 0.679 | 0.714 |
| **F1** | **0.498** | **0.517** |
| Found / extra / missed | 57 / 88 / 27 | 60 / 88 / 24 |
| kind accuracy (on found) | 0.86 | 0.817 |
| category accuracy (on found) | 0.807 | 0.817 |
| min_years accuracy (on found) | 0.965 | 0.967 |

**2. Skill names** (on the sentences found: are the skill_terms right?)

| Measure | `job-v3` | `job-v4` |
|---|---|---|
| Precision | 1.0 | 0.432 |
| Recall | 0.039 | 0.818 |
| **F1** | **0.075** | **0.565** |
| Right / wrong / missing | 3 / 0 / 74 | 63 / 83 / 14 |

**3. Strict** (full requirement: right sentence AND a shared skill name)

| Measure | `job-v3` | `job-v4` |
|---|---|---|
| F1 | 0.175 | 0.43 |
| Correct / extra / missed | 22 / 126 / 82 | 64 / 130 / 40 |

**Other**

| Measure | `job-v3` | `job-v4` |
|---|---|---|
| Invented quotes dropped by guardrails | 10 | 10 |
| Offers with no valid card | 0 | 0 |
| Mean latency per offer (s) | 34.0 | 40.2 |
| Stable across repeats | 10/10 | 10/10 |

Per offer (sentences F1 / skills F1):

| Offer | sentences | `job-v3` | `job-v4` |
|---|---|---|---|
| usajobs-883161100 | 6 | 0.476 / 0.0 | 0.476 / 0.667 |
| usajobs-883337000 | 16 | 0.462 / 0.0 | 0.462 / 0.167 |
| usajobs-883386100 | 5 | 0.222 / 0.0 | 0.222 / 0.0 |
| usajobs-883511200 | 6 | 0.414 / 0.0 | 0.414 / 0.706 |
| usajobs-883699600 | 18 | 0.973 / 0.154 | 0.973 / 0.688 |
| usajobs-883827900 | 3 | 0.25 / 0.0 | 0.25 / 1.0 |
| usajobs-884301900 | 10 | 0.667 / 0.0 | 0.667 / 0.333 |
| usajobs-884783000 | 6 | 0.667 / 0.0 | 0.667 / 0.7 |
| usajobs-885947600 | 12 | 0.211 / 0.0 | 0.455 / 0.0 |
| usajobs-886071700 | 2 | 0.19 / 0.0 | 0.19 / 0.0 |
