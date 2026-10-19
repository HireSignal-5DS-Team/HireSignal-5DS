# T11b — Fix the anonymiser taking a skill phrase as the candidate's name (small task)

Read `CLAUDE.md` first. **Start only after T10b is finished and reported.**

Approver answers to the T11 questions (Yassine, 2026-10-18):
1. **Keep the leakage check inside `/profile`**, before the Matcher. In docs and the report, describe the Bias Auditor as two parts: a guard before the Matcher (masks protected lines) + the live swap test after it (station 5). No new n8n node.
2. **Fix the header-name over-masking**: this task.
3. **No ablation for age, family or native language.** Production evidence (100% identical Matcher input) is enough. State it as a limit in `docs/BIAS_REPORT.md`.

## Problem
On CVs with section headings, `services/profile/detect.py` sometimes takes a skill or project phrase as the "name": "Qlik Sense", "Kaggle Notebooks", "Recommendation System", "Cassava Leaf Disease" (P06, P43, P45, P49). That phrase is then masked everywhere in the CV:
- real skills are removed from the Matcher's input, which can cause false MISSING / rejects;
- the live swap gets a wrong "name" to replace;
- it causes the 24 non-identical name-gender variants in T11.

## What to do
- Find why these phrases are picked as names. Add a guard so a candidate name is rejected when it looks like a skill or tech phrase. For example:
  - it matches an ESCO label or alt label (`rag/data/esco/`);
  - it matches a requirement `skill_terms` entry or the T06 tech-word guard;
  - it contains typical tech or project words;
  - it is followed by tech context.
- Keep the T11 bare-name fix working ("Fatma Trabelsi" on line 1 must still be masked). Do not weaken real-name detection: re-run the anonymiser evaluation (false names / missed names, as in T07: 45 → 1) and report before/after. No new missed names are allowed.
- Re-run the bias production check for the name-gender family on the 4 affected pairs (+ the base). The target is Matcher input identical in 312/312. Then re-run the real chain for the affected pairs and report whether any requirement decision changed vs before the fix (it may improve if a skill comes back).
- Tests:
  - "Qlik Sense" / "Recommendation System" are not taken as names;
  - "Fatma Trabelsi" is still masked;
  - no regression in `tests/test_bias.py` and the anonymiser tests.
- `pytest -q` must pass.

## Report
Write a short `tasks/T11b_report.md`: the cause, the fix, the anonymiser before/after, the new neutralisation number for name-gender, any decision changes on the affected pairs, and problems. Update `docs/BIAS_REPORT.md` with the new number and the two-part description. No git. Stop llama-server, the API and Ollama at the end.
