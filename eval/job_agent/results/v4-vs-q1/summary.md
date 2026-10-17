**Job Agent evaluation** (2026-10-17, 10 real offers, 104 gold requirements, model `hf.co/numind/NuExtract-2.0-2B-GGUF:Q4_K_M, hf.co/unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M`, mode `chat, inline`, repeat 1)

**1. Requirement sentences found** (main score: did the agent find each requirement of the offer?)

| Measure | `job-v4` | `job-q1` |
|---|---|---|
| Precision | 0.576 | 0.651 |
| Recall | 0.679 | 0.667 |
| **F1** | **0.623** | **0.659** |
| Found / extra / missed | 57 / 42 / 27 | 56 / 30 / 28 |
| kind accuracy (on found) | 0.86 | 0.821 |
| category accuracy (on found) | 0.807 | 0.786 |
| min_years accuracy (on found) | 0.947 | 0.929 |

**2. Skill names** (on the sentences found: are the skill_terms right?)

| Measure | `job-v4` | `job-q1` |
|---|---|---|
| Precision | 0.461 | 0.578 |
| Recall | 0.844 | 0.797 |
| **F1** | **0.596** | **0.67** |
| Right / wrong / missing | 65 / 76 / 12 | 59 / 43 / 15 |

**3. Strict** (full requirement: right sentence AND a shared skill name)

| Measure | `job-v4` | `job-q1` |
|---|---|---|
| F1 | 0.523 | 0.578 |
| Correct / extra / missed | 68 / 88 / 36 | 63 / 51 / 41 |

**Other**

| Measure | `job-v4` | `job-q1` |
|---|---|---|
| Invented quotes dropped by guardrails | 10 | 1 |
| Offers with no valid card | 0 | 0 |
| Mean latency per offer (s) | 41.5 | 112.7 |
| Stable across repeats | not measured (repeat 1) | not measured (repeat 1) |

Per offer (sentences F1 / skills F1):

| Offer | sentences | `job-v4` | `job-q1` |
|---|---|---|---|
| usajobs-883161100 | 6 | 0.667 / 0.667 | 0.8 / 0.846 |
| usajobs-883337000 | 16 | 0.5 / 0.308 | 0.455 / 0.118 |
| usajobs-883386100 | 5 | 0.364 / 0.0 | 0.571 / 0.0 |
| usajobs-883511200 | 6 | 0.667 / 0.706 | 0.667 / 0.923 |
| usajobs-883699600 | 18 | 1.0 / 0.653 | 1.0 / 0.795 |
| usajobs-883827900 | 3 | 0.5 / 1.0 | 0.444 / 0.0 |
| usajobs-884301900 | 10 | 0.696 / 0.457 | 0.571 / 0.105 |
| usajobs-884783000 | 6 | 0.923 / 0.609 | 0.923 / 0.933 |
| usajobs-885947600 | 12 | 0.2 / 0.364 | 0.375 / 0.8 |
| usajobs-886071700 | 2 | 0.267 / 0.0 | 0.308 / 0.0 |
