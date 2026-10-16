# Examples (val, LIVE SLM on replayed LIVE LoRA Matcher outputs)

## Accepted on the first try

- `val-005` r1 (MET): MET: the CV states "Led the migration of reporting jobs to Pandas."
- `val-005` r3 (MET): MET: the CV states "Spoken languages: Spanish (C2)."
- `val-005` r4 (MISSING): MISSING: the CV states "Bachelor's degree in Marketing (2012)."
- `val-005` r5 (MET): MET: the CV states "Angular in daily use for 5 years."
- `val-006` r1 (UNCERTAIN): UNCERTAIN: the quoted CV text shows fewer years than required; a human reviewer must check it.
- `val-006` r3 (MISSING): MISSING: the CV states "Did not use Django; the team chose other tools."

## Accepted after the corrective retry

- `val-009` summary (): Of 4 requirements, 0 are MET, 2 are MISSING, and 2 are UNCERTAIN. 0 of the must-have requirements are MET, and 4 of the requirements need human review.
  - rejected attempt: `{"summary": "Of 4 requirements, 0 are MET, 2 are MISSING, and 2 are UNCERTAIN. 0 of the must-have requirements are MET, and 4 of the must-have requirements are met. 4 of the requirements need human review."}` — count_mismatch:'4 of the must-have requirements are met' but the facts give must-have MET = 0
- `val-022` summary (): Of 5 requirements, 1 is MET, 4 are MISSING. 1 of 5 must-have requirements is MET. 4 of 5 need human review.
  - rejected attempt: `{"summary": "Of 5 requirements, 1 is MET, 4 are MISSING, and 0 are UNCERTAIN. 1 of 2 must-have requirements is MET. 4 of 5 requirements need human review."}` — number_not_in_facts:2; count_mismatch:'1 of 2 must-have requirements is MET' but the facts give 5 must-have requirements

## Fallen back to the deterministic text

- `val-005` summary (): 5 requirement(s) were checked against the CV: 4 MET, 1 MISSING and 0 UNCERTAIN. 3 of 4 must-have requirement(s) are MET. 2 requirement(s) need human review.
  - rejected attempt: `{"summary": "Of 5 requirements, 4 are MET, 1 is MISSING, and 0 are UNCERTAIN. 3 of 4 must-have requirements are MET, and 1 requirement needs human review."}` — count_mismatch:'1 requirement needs human review' but the facts give need human review = 2
  - rejected attempt: `{"summary": "Of 5 requirements, 4 are MET, 1 is MISSING and 0 are UNCERTAIN. 3 of 4 must-have requirements are MET, 1 requirement needs human review."}` — count_mismatch:'1 requirement needs human review' but the facts give need human review = 2
- `val-005` r2 (MET): MET: the CV states "Modelled 40 relational tables with primary keys, foreign keys and indexes for the HR system." A human reviewer must check it.
  - rejected attempt: `{"note": "MET: the CV states \"Modelled 40 relational tables with primary keys, foreign keys, and indexes for the HR system.\""}` — quote_not_in_facts:Modelled 40 relational tables with prima
  - rejected attempt: `{"note": "MET: the CV states \"Modelled 40 relational tables with primary keys, foreign keys, and indexes for the HR system.\""}` — quote_not_in_facts:Modelled 40 relational tables with prima
- `val-006` summary (): 6 requirement(s) were checked against the CV: 0 MET, 4 MISSING and 2 UNCERTAIN. 0 of 5 must-have requirement(s) are MET. 5 requirement(s) need human review.
  - rejected attempt: `{"summary": "Of 6 requirements, 0 are MET, 4 are MISSING, and 2 are UNCERTAIN. 5 of 5 must-have requirements are missing, and 1 is missing as well. 1 requirement is missing as well for a human review."}` — term_not_in_facts:well; count_mismatch:'5 of 5 must-have requirements are missing' but the facts give must-have MISSING = 3; count_mismatch:'1 is missing as well' but the facts give all MISSING = 4; count_mismatch:'1 requirement is missing as well for a human review' but the facts give need human review = 5
  - rejected attempt: `{"summary": "Of 6 requirements, 0 are MET, 4 are MISSING, and 1 is UNCERTAIN. 1 must-have requirement is missing, and 1 is missing for human review."}` — count_mismatch:'1 is UNCERTAIN' but the facts give all UNCERTAIN = 2; count_mismatch:'1 must-have requirement is missing' but the facts give must-have MISSING = 3; count_mismatch:'1 is missing for human review' but the facts give need human review = 5
- `val-006` r2 (UNCERTAIN): UNCERTAIN: the CV evidence is unclear or partial. A human reviewer must check it.
  - rejected attempt: `{"note": "UNCERTAIN: the evidence_quotes are empty, and the requirement is ambiguous."}` — json_key_in_text:evidence_quotes; term_not_in_facts:empty
  - rejected attempt: `{"note": "UNCERTAIN: the evidence does not provide any supporting information; a human reviewer must check it."}` — term_not_in_facts:information; decision_claim:NOT_DOCUMENTED
- `val-007` r2 (MET): MET: the CV states "Modelled 40 relational tables with primary keys, foreign keys and indexes for the HR system." A human reviewer must check it.
  - rejected attempt: `{"note": "MET: the CV states \"Modelled 40 relational tables with primary keys, foreign keys, and indexes for the HR system.\""}` — quote_not_in_facts:Modelled 40 relational tables with prima
  - rejected attempt: `{"note": "MET: the CV states \"Modelled 40 relational tables with primary keys, foreign keys, and indexes for the HR system.\""}` — quote_not_in_facts:Modelled 40 relational tables with prima
- `val-008` r3 (UNCERTAIN): UNCERTAIN: the CV evidence is unclear or partial. A human reviewer must check it.
  - rejected attempt: `{"note": "UNCERTAIN: the CV does not mention any evidence supporting the requirement; a human reviewer must check it."}` — decision_claim:NOT_DOCUMENTED
  - rejected attempt: `{"note": "UNCERTAIN: the evidence_quotes are empty, and the requirement is ambiguous."}` — json_key_in_text:evidence_quotes; term_not_in_facts:empty
