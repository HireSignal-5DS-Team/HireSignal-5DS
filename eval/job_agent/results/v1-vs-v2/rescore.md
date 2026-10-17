**Job Agent evaluation** (2026-10-17, re-scored 2026-10-17, 10 real offers, 104 gold requirements, model `hf.co/numind/NuExtract-2.0-2B-GGUF:Q4_K_M`, mode `inline`, repeat 2)

**1. Requirement sentences found** (main score: did the agent find each requirement of the offer?)

| Measure | `job-v1` | `job-v2` |
|---|---|---|
| Precision | 0.391 | 0.372 |
| Recall | 0.321 | 0.381 |
| **F1** | **0.353** | **0.376** |
| Found / extra / missed | 27 / 42 / 57 | 32 / 54 / 52 |
| kind accuracy (on found) | 0.963 | 0.938 |
| category accuracy (on found) | 0.407 | 0.406 |
| min_years accuracy (on found) | 1.0 | 1.0 |

**2. Skill names** (on the sentences found: are the skill_terms right?)

| Measure | `job-v1` | `job-v2` |
|---|---|---|
| Precision | 0.65 | 0.579 |
| Recall | 0.302 | 0.25 |
| **F1** | **0.413** | **0.349** |
| Right / wrong / missing | 13 / 7 / 30 | 11 / 8 / 33 |

**3. Strict** (full requirement: right sentence AND a shared skill name)

| Measure | `job-v1` | `job-v2` |
|---|---|---|
| F1 | 0.223 | 0.168 |
| Correct / extra / missed | 20 / 55 / 84 | 16 / 71 / 88 |

**Other**

| Measure | `job-v1` | `job-v2` |
|---|---|---|
| Invented quotes dropped by guardrails | 24 | 2 |
| Offers with no valid card | 2 | 3 |
| Mean latency per offer (s) | 45.8 | 59.6 |
| Stable across repeats | 9/10 | 7/10 |

Per offer (sentences F1 / skills F1):

| Offer | sentences | `job-v1` | `job-v2` |
|---|---|---|---|
| usajobs-883161100 | 6 | 0.0 / 0.0 | 0.0 / 0.0 |
| usajobs-883337000 | 16 | 0.214 / 0.8 | 0.0 / 0.0 |
| usajobs-883386100 | 5 | 0.333 / 0.0 | 0.0 / 0.0 |
| usajobs-883511200 | 6 | 0.714 / 0.8 | 0.6 / 0.571 |
| usajobs-883699600 | 18 | 0.973 / 0.244 | 0.973 / 0.333 |
| usajobs-883827900 | 3 | 0.0 / 0.0 | 0.16 / 0.0 |
| usajobs-884301900 | 10 | 0.0 / 0.0 | 0.421 / 0.0 |
| usajobs-884783000 | 6 | 0.0 / 0.0 | 0.182 / 0.0 |
| usajobs-885947600 | 12 | 0.0 / 0.0 | 0.0 / 0.0 |
| usajobs-886071700 | 2 | 0.0 / 0.0 | 0.4 / 0.0 |
