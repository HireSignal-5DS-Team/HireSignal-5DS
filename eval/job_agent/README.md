# Job Agent evaluation set (T15)

Copied read-only from team V2: `eval/job_agent/` (feature/agent-integration @ a5a03ff).

- `offers/`: 10 USAJOBS job offers, verbatim. They are public domain (US federal government work); see
  `offers/SOURCES.md`.
- `gold/`: V2's hand-made requirement cards for these offers (104 requirements; V2's annotation rules are in
  `ANNOTATION_RULES.md`).

Our own 4 Djinni job posts (`data/processed/jobs/J1..J4.txt`, MIT) are added by `scripts/eval_job_prompts.py`. Their
gold is the recruiter-confirmed card (`J*_requirements.json`).

Split (fixed before any run, by sorted id): dev = the first 5 USAJOBS offers + J1, J2; test = the other 5 + J3, J4.
