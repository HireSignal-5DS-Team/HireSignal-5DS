# T15 — Before/after iteration for the Job Agent and Profile Agent prompts (time-box ~1.5 h)

Read `CLAUDE.md` first. **Why:** the teacher's presentation outline asks for "at least one before-and-after example per key prompt". `job/v1.md` and `profile/v1.md` have no measured iteration (PROMPT_LIBRARY "Not done"). Approver decision, Yassine, 2026-10-19.

Rules as always: choose on dev, report test once. Keep v1 files unchanged and add v2 files. Do not touch the Matcher prompt (the LoRA was trained on it).

## Part A — Job Agent v1 → v2
- **Evaluation set:**
  - our 4 job posts (J1–J4) against their gold requirement lists (the recruiter-confirmed cards, `data/processed/jobs/J*_requirements.json`);
  - plus V2's reviewed job set if it exists (read-only from `V2_REPO`, e.g. the 10 USAJOBS offers used for "sentence F1 0.659"), split dev/test.
  - If V2's set is missing, use J1–J4 only and say so. With 4 jobs, report per job and do not tune thresholds on them.
- **Measures:**
  - requirement recall / precision / F1 (match to gold by text overlap or embedding similarity; document the rule);
  - must vs nice accuracy;
  - invented requirements;
  - verbatim-quote rate;
  - soft traits wrongly kept as must-haves;
  - wrong splits / merges;
  - latency.
- **v2:** fix the failures seen so far:
  - soft traits ("willingness to do research") are not must-haves;
  - one requirement per idea (no wrong splits or merges);
  - explicit must/nice cues ("required", "a plus", "nice to have");
  - keep quotes verbatim.

  Use few-shot examples taken from the **dev** posts only.
- Report v1 → v2 per measure + one before/after example (a job line → v1 output → v2 output).

## Part B — Profile Agent v1 → v2
- **Evaluation set:** the 52 anonymised gold CVs + the 5 Kaggle IT PDFs (dev = the dev pairs' CVs + K01–K02; test = the rest). If V2's 10 self-written CVs with gold profiles exist (`V2_REPO`), add them for skills precision/recall.
- **Measures:**
  - truncation / `profile:partial_extraction_requires_review` rate (the known v1 failure: answers cut at 768 tokens on long CVs);
  - skills precision (each extracted skill must appear in the CV text);
  - recall of the requirement `skill_terms` that are literally in the CV;
  - experience and education items found;
  - JSON valid;
  - latency per CV.
- **v2:** fix truncation. For example: a shorter JSON per chunk (no repeated fields), chunk size or token-limit tuning chosen on dev, an explicit "list each skill once" rule. Keep the anonymised input and the same output contract.
- Report v1 → v2 + one before/after example (a CV chunk → v1 output (cut / missing) → v2 output).

## Part C — Production + docs
- Switch production to v2 **only if it is better on dev without a regression**. Otherwise keep v1 and report honestly.
- Check that the final-evaluation decisions do not change. The Matcher reads the CV text, not the profile; the final evaluation used confirmed cards. If the Job Agent v2 is adopted, run 1 e2e without a card to show it works.
- Update `prompts/PROMPT_LIBRARY.md`:
  - new rows `job-v2`, `profile-v2` with technique / failure / fix / before→after numbers;
  - remove the "Not done" note if both are done.
- Tests. `pytest -q` must pass.

## Part D — Push (approved by the Approver when he sends this task)
- Same rules as T14:
  - secret scan = 0 on everything committed, no file over 50 MB;
  - commit T14's report + T15 to the **team repo branch `v3-final`** (never `main` or other branches, no force push), then push;
  - if git asks for credentials, stop and let a team member sign in.
- Report the new commit hash.

## Report
`tasks/T15_report.md`: plain words first; the before/after tables and examples for both prompts; what went to production; the push result. Stop llama-server, the API and Ollama at the end.
