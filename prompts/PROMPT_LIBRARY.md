# HireSignal prompt library

One entry per key prompt. For each version: its role in the system, the technique,
the failures observed, and the fix. Code is the source of truth; this file explains it.

| Prompt | Agent | Model | Current | Code |
|---|---|---|---|---|
| Job requirements extraction | Job Agent | NuExtract-2.0-2B | `job-v1` | [`agents/job/prompts.py`](../agents/job/prompts.py) |

---

## Job requirements extraction

**Role.** Turns a job offer into a requirements card (`contracts/job_requirements.py`)
that the Matcher uses. Every requirement must quote the job offer exactly.

**Model.** NuExtract-2.0-2B (extraction model built on Qwen2-VL-2B, MIT), temperature 0.
NuExtract has no free-text instructions: its "prompt" is a **typed JSON template** plus
**solved examples**.

### job-v1

**Techniques**
- **Structured output.** Typed template: `verbatim-string` for `title` and `evidence`
  (forces exact copies, which code can verify), enums for `kind` and `category`
  (the model can only pick allowed values), `number` for `min_years`.
- **Few-shot (2 examples).** One English, one French. They teach what the template
  cannot say:
  - one requirement per skill: "Python and Airflow" becomes two items with the same evidence;
  - `nice` for "is a plus", "preferred", "serait un atout"; `must` otherwise;
  - `min_years` only when the text gives a number of years.
- **Guardrails outside the prompt.** The model output is never trusted directly:
  `agents/job/validate.py` checks every quote, number and must/nice choice, repairs
  what is safe to repair, and drops invented requirements (see below).

**Template**

```json
{
  "title": "verbatim-string",
  "requirements": [{
    "text": "string",
    "evidence": "verbatim-string",
    "kind": ["must", "nice"],
    "category": ["skill", "experience", "education", "certification", "language", "other"],
    "skill_terms": ["string"],
    "min_years": "number"
  }]
}
```

**Failures observed:** *to fill after the first runs on the real job offers
(`real_job_offers_20.csv`). For each failure: the job offer, what the model produced,
what was expected, and how often.*

| # | Failure | Example | Frequency | Fix in v2 |
|---|---|---|---|---|
| | | | | |

### Guardrails applied after every call (code, not prompt)

| Check | If it fails |
|---|---|
| `evidence` appears in the job offer (exact, then ignoring spaces/case, then ≥ 90% similar line) | repaired to the real text, or the requirement is **dropped** as invented |
| `min_years` matches a number of years in the quote | set to the number in the quote, or `null` if the quote has none |
| `kind` agrees with cue words ("a plus", "preferred", "atout" → nice; "required", "must", "obligatoire" → must) | corrected |
| each `skill_terms` entry appears in the quote | term removed |
| output is valid JSON | one retry; then the card is flagged `needs_human_review` |

Every repair is written to the card's `warnings`, so the recruiter and the evaluation
can see it.
