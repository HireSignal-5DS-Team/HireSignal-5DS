# Matching report — CV `cv-val-000` vs job `job-val-000`

MET 2 · MISSING 3 · UNCERTAIN 1 · must-have met 2/6 · **5 requirement(s) need human review**

_Requirement-level screening aid. No automatic rejection or hiring decision._

## r1 (must-have): React: 4 years of experience or more
- Decision: **UNCERTAIN** (ambiguous); model said UNCERTAIN
- Explanation (model): The CV only partly or indirectly addresses this requirement.
- Validator: uncertain_decision
- Bias audit: PASS
- NLI judge: NOT_APPLICABLE
- Human review: **REQUIRED** — validator:uncertain_decision, decision:uncertain

## r2 (must-have): Portuguese at C1 level or above
- Decision: **MET** (supported); model said MET
- Evidence: "Spoken languages: Portuguese (C2)" (chars 282-315)
- Explanation (model): The CV directly shows this requirement; the quote is copied from the CV.
- Validator: no issue
- Bias audit: PASS
- NLI judge: PASS (score 0.9841)
- Human review: not required

## r3 (must-have): Working knowledge of Pandas
- Decision: **MISSING** (not_documented); model said MISSING
- Explanation (model): The CV says nothing about this requirement.
- Validator: must_have_absence_of_evidence
- Bias audit: PASS
- NLI judge: PASS (score 0.9999)
- Human review: **REQUIRED** — validator:must_have_absence_of_evidence

## r4 (must-have): Microsoft Azure Administrator Associate certification
- Decision: **MISSING** (contradicted); model said MISSING
- Evidence: "Enrolled in a Microsoft Azure Administrator Associate preparation course." (chars 334-407)
- Explanation (model): The CV shows this requirement is not met; the quote is copied from the CV.
- Validator: must_have_contradicted
- Bias audit: PASS
- NLI judge: UNCERTAIN (score 0.0005)
- Human review: **REQUIRED** — validator:must_have_contradicted, judge:uncertain

## r5 (must-have): Ability to design cloud architecture
- Decision: **MET** (supported); model said MET
- Evidence: "Hired to engineer cloud architecture for a multi-region SaaS product." (chars 145-214)
- Explanation (model): The CV directly shows this requirement; the quote is copied from the CV.
- Validator: no issue
- Bias audit: PASS
- NLI judge: UNCERTAIN (score 0.8484)
- Human review: **REQUIRED** — judge:uncertain

## r6 (must-have): Working knowledge of FastAPI
- Decision: **MISSING** (not_documented); model said MISSING
- Explanation (model): The CV says nothing about this requirement.
- Validator: must_have_absence_of_evidence
- Bias audit: PASS
- NLI judge: PASS (score 0.9999)
- Human review: **REQUIRED** — validator:must_have_absence_of_evidence
