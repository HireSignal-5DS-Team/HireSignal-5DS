# T11b — Fix: anonymiser takes a skill/project heading as the candidate's name (small task)

Read `CLAUDE.md` first. **Start only after T10b is finished and reported.** Approver decision (Yassine, 2026-10-18), from T11 question 2.

## Problem (from T11)
On CVs with section headings, the anonymiser sometimes takes a tech phrase as the "name" and masks it everywhere ("Qlik Sense", "Kaggle Notebooks", "Recommendation System", "Cassava Leaf Disease"; pairs P06, P43, P45, P49). This:
- removes real skills from the Matcher's input, which can cause wrong MISSING decisions;
- gives the live swap a wrong "name" to replace;
- causes the 24 non-identical name-gender variants in T11.

## What to do
1. **Find every case:** run the anonymiser on all CVs we have (52 gold pairs + counterfactual bases) and list each detected "name" that is not a plausible person name. Save it as `eval/results/<date>_name_overmask/before.csv` (cv, detected name, why it was picked). Never print real identity values in the report, only the CV id and the phrase category.
2. **Fix the name picker** (`services/profile/detect.py` / `anonymise.py`), for example:
   - reject candidates that match the ESCO labels/alt labels, the tech-word guard or the section-heading list;
   - reject candidates with no person-name shape (words that are tech terms, more than 4 words, digits);
   - when unsure, **do not mask a skill**: prefer a `name_uncertain` info flag over removing a tech phrase.

   Tune the rules on dev CVs only. Keep the T03/T07 anonymiser results: false names must not go back up (T07: 45 → 1), and no real name may leak (check against the existing anonymiser tests and the T11 counterfactual names).
3. **Re-measure:**
   - the T11 neutralisation table for name-gender (target: 312/312 identical, or explain each remaining case);
   - the requirement decisions on the affected pairs (re-run only those pairs through the chain, production settings), before vs after, against gold.
4. Tests: one per fixed phrase type, plus "real name still masked" and "skill not masked". `pytest -q` must pass.

## Report
Write a short `tasks/T11b_report.md`: before/after list (counts only), neutralisation result, decision changes on the affected pairs, problems. Update `docs/BIAS_REPORT.md` (the limits section) if the numbers change. No git. Stop llama-server, the API and Ollama at the end.
