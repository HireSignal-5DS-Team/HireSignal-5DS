**Job Agent evaluation** (2026-10-17, 10 real offers, 104 gold requirements, model `hf.co/numind/NuExtract-2.0-2B-GGUF:Q4_K_M`, mode `inline`, repeat 2)

**1. Requirement sentences found** (main score: did the agent find each requirement of the offer?)

| Measure | `job-v4` |
|---|---|
| Precision | 0.576 |
| Recall | 0.679 |
| **F1** | **0.623** |
| Found / extra / missed | 57 / 42 / 27 |
| kind accuracy (on found) | 0.86 |
| category accuracy (on found) | 0.807 |
| min_years accuracy (on found) | 0.947 |

**2. Skill names** (on the sentences found: are the skill_terms right?)

| Measure | `job-v4` |
|---|---|
| Precision | 0.461 |
| Recall | 0.844 |
| **F1** | **0.596** |
| Right / wrong / missing | 65 / 76 / 12 |

**3. Strict** (full requirement: right sentence AND a shared skill name)

| Measure | `job-v4` |
|---|---|
| F1 | 0.523 |
| Correct / extra / missed | 68 / 88 / 36 |

**Other**

| Measure | `job-v4` |
|---|---|
| Invented quotes dropped by guardrails | 10 |
| Offers with no valid card | 0 |
| Mean latency per offer (s) | 45.0 |
| Stable across repeats | 10/10 |

Per offer (sentences F1 / skills F1):

| Offer | sentences | `job-v4` |
|---|---|---|
| usajobs-883161100 | 6 | 0.667 / 0.667 |
| usajobs-883337000 | 16 | 0.5 / 0.308 |
| usajobs-883386100 | 5 | 0.364 / 0.0 |
| usajobs-883511200 | 6 | 0.667 / 0.706 |
| usajobs-883699600 | 18 | 1.0 / 0.653 |
| usajobs-883827900 | 3 | 0.5 / 1.0 |
| usajobs-884301900 | 10 | 0.696 / 0.457 |
| usajobs-884783000 | 6 | 0.923 / 0.609 |
| usajobs-885947600 | 12 | 0.2 / 0.364 |
| usajobs-886071700 | 2 | 0.267 / 0.0 |
