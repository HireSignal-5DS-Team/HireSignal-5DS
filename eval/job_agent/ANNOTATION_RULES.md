# Annotation rules for the Job Agent gold cards

The gold cards in `gold/` are the correct answers the Job Agent is measured against.
They follow these rules, so that the agent, the reviewers and the report all agree on
what a "requirement" is. Gold cards are drafts until a team member has reviewed them
(`reviewed_by` in `gold/STATUS.md`).

## 1. What counts as a requirement

Something the **candidate** must have, that a recruiter could check on a CV:

| Include | Example |
|---|---|
| degrees and fields of study | "Bachelor's degree in Computer Science" |
| years or level of experience | "Minimum of 3 years of relevant professional experience" |
| specific experience | "Experience deploying and operating applications in Kubernetes environments" |
| skills, tools, methods | "Proficiency using git (particularly GitLab)" |
| certifications | "AWS certification" |
| languages | "Fluent French" |
| preferred / desired qualifications | marked `nice` |

| Exclude (never a requirement) | Why |
|---|---|
| job duties and responsibilities ("You will build…", "Duties") | what the job does, not what the candidate has |
| legal and administrative conditions: citizenship, residency, background check, drug test, Selective Service, security clearance, probation, time in grade | not on a CV; citizenship-type criteria must not drive screening |
| application instructions: résumé length, transcripts, questionnaires, deadlines | about the application, not the candidate |
| assessment competency lists ("You will be assessed on: Attention to Detail, Customer Service…") | how candidates are rated later, not entry requirements |
| benefits, salary, location, agency description | not about the candidate |

**Offers with several grade levels** (e.g. ZP-III and ZP-IV, GS-12/13): the gold card uses
the **entry level** only. Requirements of higher levels are not counted.

**Alternative paths** ("one year of specialized experience **OR** a Ph.D. **OR** a
combination of education and experience"): the main path is annotated; the substitutes
are not separate requirements.

## 2. One requirement = one thing to check

- Skills joined by **and / commas / et** are split: "Docker and Kubernetes" → 2 requirements.
- Skills given as **alternatives** stay one requirement: "PostgreSQL **or** Oracle".
- A list introduced by **such as / e.g. / including / like / notamment / tels que** gives
  examples and stays one requirement: "ETL tools such as Pentaho, AWS Glue and Airflow".
- Education is never split ("degree in mathematics, statistics or computer science" is one).

## 3. Fields

- `evidence`: the shortest **exact** sentence or clause of the offer that states the
  requirement, copied character for character.
- `text`: the requirement as a short statement (for split items: the sentence with only that skill).
- `kind`: `must`, unless the wording or the section says optional ("Preferred
  Qualifications", "desired", "a plus", "ideally") → `nice`.
- `category`: `education` (degrees), `experience` (years or "experience with/in…"),
  `certification`, `language`, `skill` (knowledge, proficiency, ability), `other`.
- `skill_terms`: the named skills the requirement asks for, as written in the offer (rules below).
- `min_years`: only when the offer gives a number of years for that requirement; else `null`.

### 3.1 `skill_terms`

`skill_terms` has two jobs. The Matcher looks for these names on the CV, and the code splits a
line into one requirement per term (§2). So a term must be **something a candidate could list
on a CV** and **what the requirement asks for**, not a detail around it.

| # | Rule | Example (terms in **bold**) |
|---|---|---|
| S1 | Terms are the **objects of the requirement**: what follows "experience with / in / using", "knowledge of", "proficiency in", "expertise in", or the skill a duty-style line names. Words about purpose, context or parts are not terms | "Experience with **computer programming** and **tool development** to solve key AI measurement science challenges"; "designing … end-to-end **AI platforms** that incorporate secure data pipelines, APIs…" |
| S2 | After **such as / e.g. / including / to include / particularly**, every **named** example is a term. The general word before the list is a term only if it is itself a named skill, not a generic class | "**ETL** … tools such as **Pentaho**, **AWS Glue**"; "**git** (particularly **GitLab**)"; "statistical software or programming languages (e.g., **R**, **Python**)": no term for "statistical software" |
| S3 | **Boundary**: the shortest form a CV would use. Drop a trailing generic noun (practices, pipelines, projects, techniques, tools, patterns, skills, technologies) when the rest is a skill on its own; keep it when the rest is not | "**CI/CD** pipelines", "**DevOps** practices", "**RPA** projects"; but "**data pipelines**", "**RESTful APIs**", "**distributed systems**" |
| S4 | A full name with its acronym in parentheses is **one term, the first form written**. A pair written as one unit with a slash stays one term | "**Microsoft SQL Server** (MSSQL)", "**robotic process automation** (RPA)", "**artificial intelligence/machine learning** (AI/ML)" |
| S5 | **Never terms**: verbs and activities (designing, troubleshooting), adjectives (secure, scalable), generic nouns (data, code, applications, environments, solutions), grade levels (GS-13), generic experience labels ("IT-related experience", "specialized experience"), generic classes ("modern programming languages", "cloud tools") | "Experience troubleshooting **distributed systems** and production environments": not "troubleshooting", not "production environments" |
| S6 | **Education** items have no terms (the field of study is in `text`). A **soft skill** is a term only when the offer lists it as a named competency on its own line | "Bachelor's degree in computer science" → `[]`; "**Teamwork**" (competency line) → `["Teamwork"]` |

No limit on the number of terms: every name that passes S1–S6 is listed, and none that fails.
A sentence with no such name has `skill_terms: []`.

## 4. Evaluation matching (`scripts/eval_job_agent.py`)

A predicted requirement matches a gold one when their quotes overlap (one contains the
other, or ≥ 60% similar) **and** they share a skill term (or, without skill terms, their
texts are similar). Each gold requirement matches at most one prediction.
Reported: precision, recall, F1, and on matched pairs the accuracy of `kind`,
`category` and `min_years`; plus invented quotes, latency and run-to-run stability.
