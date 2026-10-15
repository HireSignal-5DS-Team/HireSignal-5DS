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
- `skill_terms`: the tool / technology / domain names, as written in the offer.
- `min_years`: only when the offer gives a number of years for that requirement; else `null`.

## 4. Evaluation matching (`scripts/eval_job_agent.py`)

A predicted requirement matches a gold one when their quotes overlap (one contains the
other, or ≥ 60% similar) **and** they share a skill term (or, without skill terms, their
texts are similar). Each gold requirement matches at most one prediction.
Reported: precision, recall, F1, and on matched pairs the accuracy of `kind`,
`category` and `min_years`; plus invented quotes, latency and run-to-run stability.
