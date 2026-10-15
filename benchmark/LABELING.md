# Labeling policy (val / test / train)

Gold labels are per requirement and follow `matcher.validate.CONSISTENT`. They judge what the CV *documents*, never
whether the person is a good hire.

| Gold | When | Evidence |
|---|---|---|
| `MET` / `supported` | The CV explicitly shows the requirement (same skill, a true equivalent, enough years, the certificate/degree/language level). | Required |
| `MISSING` / `not_documented` | The CV says nothing about it. This is absence of evidence, **not** proof that the person lacks the skill. | Empty |
| `MISSING` / `contradicted` | The CV explicitly shows a shortfall or negation: fewer years, a lower CEFR level, a lower degree listed as the highest or only qualification, "no experience with X", a certificate that is expired, in preparation or not held. | Required |
| `UNCERTAIN` / `ambiguous` | Partial, implied or vague: "worked with Docker on several projects" for "3+ years Docker", a self-rated level below the required one ("basic", "intermediate" vs "advanced"), a neighbouring version or certificate level (Vue 2 vs Vue 3, ITIL v3 vs ITIL 4), a duration that depends on how a role is counted, or a job requirement that contradicts itself ("entry level, 10+ years"). | Optional |

Rules
- **Gold evidence** is the minimal exact CV substring(s) that justify the label. A whole CV line is fine. Several
  quotes are allowed (e.g. role dates plus the line naming the skill).
- **Equivalence** counts as MET only for true equivalents: Postgres = PostgreSQL, K8s = Kubernetes,
  RHEL/Ubuntu servers = Linux administration, PSPO I = Professional Scrum Product Owner, an
  "Oracle ... Certified Professional" = OCP. A requirement written with "e.g." accepts any tool of the named category.
- **Related but not equivalent** is never MET: MySQL for PostgreSQL, Java for JavaScript, Azure for AWS, Tableau for
  Power BI, Puppet for Ansible, CCNA for CCNP, Kanban for Scrum. Default label is `MISSING/not_documented`;
  `UNCERTAIN` when the CV states a close neighbour that could partly satisfy the requirement.
- **Knowledge is not evidence.** ESCO entries describe terminology; if ESCO lists an alias (e.g. "tensorflow" under
  computer vision) that the CV mentions for another purpose, the requirement is still not MET (`rag_only_term`).
  `rag_only_term` also marks requirements phrased with an ESCO term or alias that the CV writes differently
  ("extract, transform, load" vs "ETL", "directory services" vs "Active Directory").
- **Years**: computed from explicit numbers ("6 years", "5+ years", "10 yrs") or from role date ranges when the skill
  is named in that role ("Jul 2021 – present", reference year 2026). "4+ years" for a 5-year minimum is `UNCERTAIN`
  (lower bound only). Total career length does not count for a specific skill.
- **Languages** use CEFR order A1 < A2 < B1 < B2 < C1 < C2 < native. A level without CEFR grade ("conversational",
  a bare language name) against a graded requirement is `UNCERTAIN`.
- `nice`-to-have requirements are labelled with the same rules as `must`.

Tags (several per requirement): `exact`, `equivalence`, `related_not_equivalent`, `experience_years`,
`ambiguous_duration`, `not_documented`, `negation`, `rag_only_term`, `certification`, `education`, `language`,
`contradictory_requirement`.

Splits
- `val.jsonl` (14 cases) and `test.jsonl` (14 cases) are hand-written in `benchmark/build_handwritten.py`. They use
  different CVs and job titles; test was written independently of val.
- `test.jsonl` is locked (CONTRACT.md). Model selection uses val only.
- `train.jsonl` is produced by `benchmark/generate_train.py` (seed 13) with other templates and layouts. It has no
  `rag_only_term` items, because those depend on ESCO retrieval rather than on the CV text.
- `python benchmark/check_data.py` validates all three files.
