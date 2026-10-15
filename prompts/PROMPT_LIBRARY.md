# HireSignal prompt library

One entry per key prompt. For each version: its role in the system, the technique,
the failures observed, and the fix. Code is the source of truth; this file explains it.

| Prompt | Agent | Model | Current | Code |
|---|---|---|---|---|
| Job requirements extraction | Job Agent | NuExtract-2.0-2B | `job-v2` | [`agents/job/prompts.py`](../agents/job/prompts.py) |

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

**First real run** (2026-10-15, laptop RTX 4050, Ollama, `--mode inline`,
`examples/job_post.example.txt` against the gold card `examples/job_requirements.example.json`):

| Measure | Result |
|---|---|
| Requirements found | 7 / 8 |
| Invented | 0 |
| kind correct | 7 / 7 |
| category correct | 7 / 7 |
| min_years correct | 1 / 1 |
| Quotes needing repair | 2 (both repaired by the guardrails: `fuzzy 0.93`, `spacing`) |
| Latency | 64 s (first call, includes model loading) |

**Failures observed**

| # | Failure | Example | Frequency | Fix in v2 |
|---|---|---|---|---|
| F1 | Compound requirement not split: one item for two skills, so the second skill is lost | "At least 3 years of professional experience with Java and Spring Boot." → only "…with Java", `skill_terms: ["Java"]` (Spring Boot missing entirely) | 1 of 1 compound requirements on the example | `job-v2` |
| F2 | Quote copied with small slips | "Fluent French;" (punctuation), "good written English." (case) | 2 of 7 | none needed: repaired by the guardrails |

*Results on the real job offers: see the evaluation below.*

### job-v2

**Why.** Failure F1. The model output `skill_terms: ["Java"]` for "Java and Spring Boot":
it did not just forget to split, it **lost the second skill**. Diagnosis: every v1 example
showed exactly one skill per item, so the model learned "one term per item"; producing a
second item for the same line is a harder, multi-step behaviour that a 2B model did not
copy from two examples.

**Technique: task decomposition** (give the model the easy part, give code the exact part).
- The model now makes **one item per requirement line** and lists **every** skill of that
  line in `skill_terms` (typed `["verbatim-string"]`, so the terms are copied exactly).
  The examples show compound lines with 2 and 3 skills, in English and French.
- Code (`validate.split_compound`) turns a compound item into one requirement per skill
  when the skills are joined by "and" / "et" / commas, and rewrites the text per skill
  ("…with Java", "…with Spring Boot"). Skills joined by "or" / "ou" are **alternatives**
  and stay one requirement ("PostgreSQL or Oracle": either is enough). Education is never split.
- `evidence` moved to the **first** field of the template, so the model copies the line
  before describing it.
- New examples also teach an alternatives line ("AWS or Azure", "MySQL ou PostgreSQL").

**Gold card updated.** "Docker and Kubernetes is a plus" is now two requirements (r7, r8),
following the rule "one requirement = one thing to check" (9 requirements in total).

**Before / after** (same job offer, same model, same settings; run
`python scripts\run_job_agent.py examples\job_post.example.txt --prompt job-v1` then `--prompt job-v2`):

**First job-v2 run** (2026-10-15, laptop, Ollama, `--mode inline`):

| Check against the gold card (9) | job-v1 | job-v2 (first run) |
|---|---|---|
| Java **and** Spring Boot both found (F1) | no: Spring Boot lost | **yes, fixed** |
| "PostgreSQL or Oracle" kept as one | yes | yes |
| French / English correct | yes | text wrong: "Fluent English" instead of "good written English" (F3) |
| Docker / Kubernetes found | as one item | **dropped** as invented (F4) |
| Invented requirements kept | 0 | 0 |

The prompt change worked (the model now lists both skills of a compound line), and it
exposed two failures **in the code around the model**, not in the model:

| # | Failure | Cause | Fix (code) |
|---|---|---|---|
| F3 | "Fluent French; good written English." split into "Fluent French" + "Fluent **English**" | the split assumed both skills share one phrase ("experience with Java and Spring Boot"); here they are two clauses | if the skills are separated by `;`, a sentence end or a line break, each skill gets **its own clause** as text and evidence, with its own years and must/nice (`_split_by_clause`) |
| F4 | Docker/Kubernetes quote 87% similar to the real line, under the 90% threshold, so dropped | the model quoted the line with extra words around it (exact text unknown: raw answers were not saved yet) | if the quote **contains** a whole real line, keep that line (`contained`); dropped items now show what the model quoted, and the raw answer is saved to `out/<job>.<prompt>.raw.txt` |

Lesson for the report: a better prompt can move errors downstream. Measuring the whole
agent (model + guardrails), not the model alone, is what caught F3.

**Rerun with the F3/F4 fixes** (same day): both `job-v1` and `job-v2` gave all 9 requirements.
`job-v1` lost Spring Boot in three earlier runs and found it in this one, with the same input
and temperature 0: **one example is not a valid comparison**. The model was not fully
reproducible (Ollama split the work differently between CPU and GPU across runs), so a fixed
`seed` is now sent with every request, and the comparison is made on 10 real offers.

### Evaluation on real job offers

10 USAJOBS offers, 104 gold requirements, rules in
[`eval/job_agent/ANNOTATION_RULES.md`](../eval/job_agent/ANNOTATION_RULES.md); run
`scripts/eval_job_agent.py`. *Results table to paste here from `eval/job_agent/results/<name>/summary.md`.*

Drafting the gold cards (before any model run) exposed four more guardrail bugs, now fixed and tested:

| # | Found in | Problem | Fix |
|---|---|---|---|
| G1 | "ETL tools such as Pentaho, AWS Glue, Hadoop, and Apache Airflow" | the split made four required skills out of a list of examples | lists after "such as / e.g. / including / to include / notamment / tels que" stay one requirement |
| G2 | "CI/CD pipelines and modern DevOps practices" | the `/` inside "CI/CD" was read as "or" | only the words **between** the skills decide; "git (particularly GitLab)" stays one |
| G3 | "at least 52 weeks", "one (1) year", "one full year" | durations not recognised as years | weeks and months converted; "(1)" and "full" accepted |
| G4 | "a degree completed within the last two years" | the years check would set `min_years: 2` on an education requirement | years are only filled in automatically for experience requirements |

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
