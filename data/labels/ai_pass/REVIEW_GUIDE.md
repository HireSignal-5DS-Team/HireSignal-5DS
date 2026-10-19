# Checking the AI pre-labels (method C)

**What this is:** Claude (the project's planning assistant, an Anthropic model, NOT the Qwen model we are testing) pre-labelled the 40 real CV x job pairs on 2026-10-18. It did not see any HireSignal output. A human must now check every row. The checked labels become our ground truth.

**File:** `ai_prelabels_for_review.xlsx` (sheets: `requirements` 280 rows, `pairs` 40 rows, `job_requirements` 28 rows). Job texts: `../../processed/jobs/J1..J4.txt`. CVs: `../../processed/cvs/<cv_file>`.

## Your steps
1. **Requirements first (`job_requirements`, ~15 min):** read each job and check the 28 requirements. Note any you would change in `notes` and tell the team. Suggestions from the AI pass are listed below.
2. **Each requirement row (`requirements`):** open the CV, read the AI decision and quote.
   - If you agree: put **OK** in column K.
   - If you disagree: put **CHANGED** in K, then your decision in L (MET / MISSING / UNCERTAIN) and your exact CV quote in M (copy-paste).
3. **Each pair (`pairs`):** OK, or CHANGED + your outcome (invite / review / reject) + one sentence.
4. Do not accept a row just because the AI wrote it: if you would have hesitated, look again. We report how many rows you changed.

Rules (same as `../LABELLING_GUIDE.md`): MET needs an exact CV quote; MISSING = contradicted or not mentioned; UNCERTAIN = partial, unclear or implied; judge only what is written; never use name, gender, age or nationality.

Time: about 1.5 hours.

## Notes from the AI pass (please judge them)
- **Requirement suggestions:**
  - J2 r6 "Willingness to research business logic" is a soft trait that CVs almost never state; it pushed P15 and P16 (strong on all technical must-haves) to review. Suggest: make it nice-to-have or remove it.
  - J1 misses one must-have from the job text: "Hands-on experience with data preparation, cleansing, feature engineering, and visualization". Suggest adding it.
  - J3 r6 bundles four things (microservices, cloud, Docker, Kubernetes): partial matches become UNCERTAIN. Acceptable, but you may split it.
- **Borderline calls to look at:** P21 (strong ML-in-production profile rejected only on J3 r6), P15 (outcome review vs invite), P03 r7 and P07 r7 (SQL counted as "strong working knowledge"), P06 r3 (MCMC counted as Bayesian), P32 r2 ("big systems").
- **Result of the AI pass:** 48 MET, 192 MISSING, 40 UNCERTAIN; outcomes: 0 invite, 4 review, 36 reject. The jobs are demanding (J1 is very niche), so **no pair is a clear invite**. This set can test reject/review, but not invite: see the team note about adding targeted pairs.

## Second file: 12 targeted pairs (`ai_prelabels_EXTRA_for_review.xlsx`), added 2026-10-18
Why: the first 40 pairs had 0 invite cases, so the Outcome gate could not be tested on invites. These 12 CVs were found by a keyword search for each job's must-have skills (no model), then pre-labelled by Claude the same way.
Check it exactly like the first file (OK / CHANGED on every row and every pair). Two extra things:
- Sheet `decisions`: J2 r6 is now **nice-to-have** (Approver's decision). Nothing to do, just know it.
- Sheet `pairs`, last row: **P15 outcome review → invite** (because J2 r6 is no longer a must-have). Mark OK or CHANGED.
About 30 minutes.
