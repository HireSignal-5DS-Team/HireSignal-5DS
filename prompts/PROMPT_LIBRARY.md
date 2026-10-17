# HireSignal prompt library

One entry per key prompt. For each version: its role in the system, the technique,
the failures observed, and the fix. Code is the source of truth; this file explains it.

| Prompt | Agent | Model | Current | Code |
|---|---|---|---|---|
| Job requirements extraction | Job Agent | NuExtract-2.0-2B | `job-v4` (since 2026-10-17: best strict F1 0.43 on the 10 real offers) | [`agents/job/prompts.py`](../agents/job/prompts.py) |

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
`scripts/eval_job_agent.py`.

**Run 1: job-v1 vs job-v2** (2026-10-17, laptop RTX 4050, Ollama, `--mode inline`, seed 0, repeat 2;
full results in `eval/job_agent/results/v1-vs-v2/`):

| Measure | `job-v1` | `job-v2` |
|---|---|---|
| Precision | 0.267 | 0.184 |
| Recall | 0.192 | 0.154 |
| **F1** | **0.223** | **0.168** |
| Correct / extra / missed | 20 / 55 / 84 | 16 / 71 / 88 |
| kind accuracy (on matched) | 0.95 | 1.0 |
| category accuracy (on matched) | 0.65 | 0.375 |
| Offers with no valid card | 2 | 3 |
| Mean latency per offer | 45.8 s | 59.6 s |
| Stable across repeats | 9/10 | 7/10 |

Both versions fail on real offers, and v2 is worse than v1: the fix that worked on the
one-page example (F1 on 9 requirements) did not carry over to 1,200–1,900-word postings.

**Error analysis** (reading the 20 saved raw answers):

| # | Error | Evidence | Share |
|---|---|---|---|
| E1 | Answer **cut off** at the 2,048-token output limit: broken JSON, whole card lost | 5 of 20 answers stop mid-sentence at ~10,000 characters | 5/20 runs |
| E2 | The model extracts **every sentence that sounds required**, not just candidate requirements | e.g. offer 883827900 (v2): 22 items, of which citizenship, probation, Selective Service, "Maximum of 2-page resume", direct deposit, E-Verify… only 2 are real requirements | most of the 126 extra items |
| E3 | **Invented categories** outside the allowed list | 181 items: `other` 67, `condition` 13, `qualification` 10, `age`, `citizenship`, `security`, `employment`… | 33% of items |
| E4 | Degenerate repetition | v1 on 883827900: 20 items with evidence "None" (all dropped by the guardrails) | 1 offer |

Why: NuExtract takes **no instructions**. Its examples only ever showed requirements, never
text to leave out, so it had no way to learn "skip citizenship". And the longer the input,
the more such sentences it sees.

**Guardrails only (no new model run).** The saved raw answers replayed through the new
guardrails (salvage of cut-off answers, category inference):

| Same saved answers | `job-v1` | `job-v2` |
|---|---|---|
| Offers with no valid card | 2 → **0** | 3 → **0** |
| category accuracy | 0.65 → 0.61 | 0.375 → **0.59** |
| F1 | 0.223 → 0.235 | 0.168 → 0.194 |

Cards are no longer lost, but F1 barely moves: E2 (wrong things extracted) dominates, and only
changing **what the model sees** can fix it. That is job-v3.

### job-v3

**Why.** E1–E3 above.

**Techniques**
- **Input selection** (`agents/job/sections.py`): only the requirement sections are sent
  (Qualifications, Requirements, Profil recherché, Education, Nice to have…); Summary, Duties,
  Conditions of employment, Benefits, How to apply are dropped, and inline boilerplate
  ("Additional information …") is cut. On the 10 offers this removes 30–70% of the text,
  and all 104 gold quotes remain inside the text sent (checked by a test).
- **Chunking**: the kept text is sent ~700 characters at a time (4–11 calls per offer), so
  every answer is short (E1) and the model sees few distracting sentences at once.
- **Negative examples**: the 3 examples are chunk-sized and *contain* text to skip
  (volunteer-work boilerplate, transcripts, location, application deadline); one example is
  only administrative conditions and its correct output is **empty** (E2).
- Only allowed categories in the examples (E3); invalid categories are re-inferred by code.
- A separate tiny call reads the job title; items found under a "Nice to have" / "Preferred"
  heading become `nice` unless their wording says required.

**Results.** Run 2: job-v2 vs job-v3 (2026-10-17, same setup as run 1, repeat 2; full results in
`eval/job_agent/results/v2-vs-v3/`). The first table used the strict score only:

| Strict score (right sentence AND a shared skill name) | `job-v2` | `job-v3` |
|---|---|---|
| F1 | 0.227 | 0.165 |
| Correct / extra / missed | 27 / 107 / 77 | 21 / 130 / 83 |
| category accuracy (on matched) | 0.63 | 0.95 |
| Stable across repeats | 3/10 | **10/10** |
| Mean latency per offer | 52.3 s | 43.1 s |

v3 looked worse. Reading the cards showed why: **the model left `skill_terms` empty on 150 of
its 151 items**. The strict score needs a shared skill name, so a requirement whose sentence
was found correctly still counted as one extra *and* one missed. The scoring was then split
into two questions (`--rescore`, `eval/job_agent/results/v2-vs-v3/rescore.md`):

| Re-scored, same saved cards | `job-v2` | `job-v3` |
|---|---|---|
| **Sentences F1** (requirement sentences found) | 0.481 | **0.500** |
| Sentences recall | 0.619 | 0.690 |
| **Skill names F1** (on the sentences found) | 0.288 | **0.075** |
| Skill names: right / wrong / missing | 15 / 16 / 58 | 3 / 0 / 74 |

So job-v3 does its main job (input selection: best recall, stable, fewer invented
categories), and loses everything on skill names. That is job-v4.

Drafting the gold cards (before any model run) exposed four more guardrail bugs, now fixed and tested:

| # | Found in | Problem | Fix |
|---|---|---|---|
| G1 | "ETL tools such as Pentaho, AWS Glue, Hadoop, and Apache Airflow" | the split made four required skills out of a list of examples | lists after "such as / e.g. / including / to include / notamment / tels que" stay one requirement |
| G2 | "CI/CD pipelines and modern DevOps practices" | the `/` inside "CI/CD" was read as "or" | only the words **between** the skills decide; "git (particularly GitLab)" stays one |
| G3 | "at least 52 weeks", "one (1) year", "one full year" | durations not recognised as years | weeks and months converted; "(1)" and "full" accepted |
| G4 | "a degree completed within the last two years" | the years check would set `min_years: 2` on an education requirement | years are only filled in automatically for experience requirements |

### job-v4

**Why.** job-v3 finds the right sentences but fills `skill_terms` on 1 item in 151. Without
skill names, compound lines are never split ("Java and Spring Boot" stays one item) and the
Matcher has nothing to compare with a CV. Upper bound measured before writing any code: giving
the saved v3 cards the gold skill names of the sentences they already found raises the strict
correct count from **21 to 59**. The bottleneck is the skill names, not the sentences.

**Technique: task decomposition, second step.** The first call (job-v3 template, examples
and chunks, unchanged) only finds the requirement sentences. Then **one focused call per
requirement sentence** asks for the skill names alone:

```json
{"skill_terms": ["verbatim-string"]}
```

- The input is one short sentence, so the model has a single job. A probe on 12 gold sentences
  returned useful terms in about 0.3 s per call.
- The sentence sent is the **real text of the offer** (the quote after the guardrails' repair),
  so verbatim terms can be found in it. Each distinct sentence is asked once. Invented quotes
  are not sent.
- 6 examples: 3 with terms (a compound list, a two-word method, French alternatives) and 3 whose
  correct answer is **empty** (a degree, years of specialized experience, a list of duties).
  The probe showed the model listing activities ("Writing", "testing") as skills.
- The new terms are added to any the first call gave. Then the existing guardrails run
  unchanged: a term must appear in the quote, and compound lines are split.

**Results.** Run 3: job-v3 vs job-v4 (2026-10-17, laptop RTX 4050, Ollama, `--mode inline`,
seed 0, repeat 2; full results in `eval/job_agent/results/v3-vs-v4/`):

| Measure | `job-v3` | `job-v4` |
|---|---|---|
| Sentences F1 | 0.498 | 0.517 |
| Sentences found / extra / missed | 57 / 88 / 27 | 60 / 88 / 24 |
| **Skill names F1** | 0.076 | **0.532** |
| Skill names precision / recall | 1.0 / 0.039 | 0.404 / **0.776** |
| Skill names right / wrong / missing | 3 / 0 / 73 | 59 / 87 / 17 |
| **Strict F1** | 0.159 | **0.409** |
| Strict correct / extra / missed | 20 / 128 / 84 | 61 / 133 / 43 |
| kind accuracy (on found sentences) | 0.86 | 0.82 |
| category accuracy (on found sentences) | 0.81 | 0.82 |
| Requirements in the 10 cards | 148 | 194 |
| Mean latency per offer | 34.0 s | 40.2 s (+6 s) |
| Stable across repeats | 10/10 | 10/10 |

The skill-name recall goes from 4% to 78%, and the strict score of the whole agent goes from
0.16 to 0.41, the best so far, for 6 s more per offer. Sentence finding is almost unchanged, as
expected: the first call is the same. The small gain comes from `_split_by_clause`, which now
receives terms and cuts some lines into their real clauses (offer 885947600: 0.21 → 0.45).

**Error analysis** (the 87 wrong skill names, on the sentences found):

| # | Error | Examples | Count |
|---|---|---|---|
| T1 | A real skill or domain that the gold card does not mark (the gold keeps one or two key terms per sentence) | "model development", "containerized workloads", "web services", "secure authentication" | 52 |
| T2 | Boundary differs from the gold term | "CI/CD pipelines" vs "CI/CD", "DevOps practices" vs "DevOps", "RESTful" + "API" vs "RESTful APIs" | 12 |
| T3 | Generic words: activities and adjectives | "designing", "implementing", "troubleshooting", "secure", "scalable" | 12 |
| T4 | Terms on a sentence with no skill in the gold (degree contents, grade levels) | "GS-13", "mathematics", "statistics", "real world environments" | 11 |

Every wrong term also produces a wrong split, which is why the card count rises from 148 to 194
and the strict "extra" count does not go down.

Reading: T3 and T4 are model errors that more empty examples or a stopword filter in code
could remove. T1 and T2 looked partly like an **annotation question**, so before tuning the
prompt for precision, the `skill_terms` rule was written down (ANNOTATION_RULES.md §3.1, rules
S1–S6: the objects of the requirement, named examples after "such as", shortest CV form, no
generic words). Applying it changed 8 of the 70 gold sentences (e.g. "IT-related experience" is
no longer a term, "Microsoft SQL Server (MSSQL), including schema design…" gains the three
methods, "RPA projects" → "RPA"); the number of gold requirements is unchanged (104).

Same saved cards, re-scored against the gold that follows the rule
(`eval/job_agent/results/v3-vs-v4/rescore.md`):

| Measure | `job-v3` | `job-v4` |
|---|---|---|
| Skill names F1 | 0.075 | **0.565** |
| Skill names precision / recall | 1.0 / 0.039 | 0.432 / 0.818 |
| Skill names right / wrong / missing | 3 / 0 / 74 | 63 / 83 / 14 |
| Strict F1 | 0.175 | **0.430** |

The score barely moves: **83 wrong terms remain wrong under the written rule**. Most of T1
are details around the requirement (S1: "secure data pipelines" in "AI platforms that
incorporate secure data pipelines…"), not skills the annotator forgot. So precision is a real
model problem, and the next prompt version can target it (examples where details are not terms,
and the S5 word list as a code filter).

Open points, not yet decided:
- "Experience using LLMs, RAG, MCP servers, and other AI development resources, including cloud
  tools such as AWS Bedrock and Azure OpenAI": S2 would add AWS Bedrock and Azure OpenAI, but
  `split_compound` would then keep the whole line as one requirement (a "such as" in any gap
  stops the split). The gold item is left unchanged until the code groups only the terms after
  the marker.
- §1 excludes "assessment competency lists", yet three gold cards keep lines such as "Attention
  to Detail", because those offers say the candidate must show these competencies. §1 needs to
  say so explicitly.

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
