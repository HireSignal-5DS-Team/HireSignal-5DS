# Labelling guide (40 CV x job pairs)

**Files:**
- **each labeler gets their own file:** labeler A fills `labelling_sheet_A.xlsx`, labeler B fills `labelling_sheet_B.xlsx`. Each file has only that labeler's columns.
- the job texts in `../processed/jobs/J1..J4.txt`
- the CVs in `../processed/cvs/<cv_id>.txt`

**Labelers:** A and B work alone. Do not open the other labeler's file, and do not use any AI tool. When both are done, the Developer merges the two files and measures agreement (`scripts/merge_labels.py`).

**Step 0 (once, together):** open the `job_requirements` sheet and check the DRAFT requirements against the job text.
- Edit, add or remove requirements if needed.
- Change `status` from DRAFT to OK.
- Tell the Developer about any change, so both files can be rebuilt before you start labelling.

## 1. One decision per requirement (`requirements` sheet)

| decision | when | CV quote |
|---|---|---|
| **MET** | The CV clearly shows the requirement. | **Required.** Copy the exact words from the CV file (copy-paste, no edits). No quote means it is not MET. |
| **MISSING** | The CV shows it is not met (for example 2 years when 4 are needed), **or** the CV says nothing about it. | Quote the contradicting text. Leave it empty if the CV says nothing. |
| **UNCERTAIN** | It is partial, unclear or only implied. | Quote the closest text if there is one. |

**Rules:**
- Judge only what is written in the CV. Do not guess what the person probably knows.
- For years, use the CV's "Experience years" line or dates written in the CV.
- Similar skills count only if they are clearly the same thing (for example "PostgreSQL" counts for "SQL"). "Some cloud" does not count for "GCP" unless the requirement says "or other cloud providers".
- Use `notes` for anything odd.

**Examples:**
- Requirement "Knowledge of Python", CV "I use Python (Django, Flask, FASTApi)": **MET**, with quote `I use Python (Django, Flask, FASTApi)`.
- Requirement "Data Science: 4 years or more", CV "Experience years: 0.5": **MISSING**, with quote `Experience years: 0.5`.
- Requirement "Experience with PySpark", and the CV only says "big data tools": **UNCERTAIN**, with quote `big data tools`.
- Requirement "Ph.D. in Mathematics", and the CV has no education section: **MISSING**, with no quote.

## 2. One outcome per pair (`pairs` sheet)

- **invite**: all must-have requirements are MET.
- **review**: one or two must-haves are UNCERTAIN, or there is a borderline case you would want a recruiter to look at.
- **reject**: one or more must-haves are clearly MISSING and nothing suggests a review would change that.
- Write one short sentence in `reason`.
- Never use name, gender, age, nationality or photo. They should not appear in these CVs; if you see any, ignore them and note it.

## 3. Time

- Each pair has 6-8 requirements. Expect about 4-6 minutes per pair, so **about 3-4 hours per labeler** for the 40 pairs (280 requirement rows).
- Plus about 20 minutes together for step 0.
- Take breaks every 10 pairs.
