# Matching report — CV `cv-val-000` vs job `job-val-000`

MET 2 · MISSING 3 · UNCERTAIN 1 · must-have met 2/6 · **4 requirement(s) need human review**

_Requirement-level screening aid. No automatic rejection or hiring decision._

Prompt `p1` · knowledge `rag.bm25`

## r1 (must-have): React: 4 years of experience or more
- Decision: **UNCERTAIN** (ambiguous); model said UNCERTAIN
- Explanation: Requirement "React: 4 years of experience or more": UNCERTAIN. The CV evidence is partial or ambiguous. Terminology from: react to physical changes or hazards, improvise, think quickly (knowledge base, not candidate evidence).
- Model text: The CV only partly or indirectly addresses this requirement.
- Validator: uncertain_decision
- Bias audit: PASS
- NLI judge: not run
- Answered by: primary · Qwen/Qwen3-4B-Instruct-2507+lora · adapter HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1
- Human review: **REQUIRED** — validator:uncertain_decision, decision:uncertain

## r2 (must-have): Portuguese at C1 level or above
- Decision: **MET** (supported); model said MET
- Evidence: "Spoken languages: Portuguese (C2)" (chars 282-315)
- Explanation: Requirement "Portuguese at C1 level or above": MET. The CV states "Spoken languages: Portuguese (C2)". Terminology from: interact verbally in Portuguese, understand spoken Portuguese, understand written Portuguese (knowledge base, not candidate evidence).
- Model text: The CV directly shows this requirement; the quote is copied from the CV.
- Validator: no issue
- Bias audit: PASS
- NLI judge: not run
- Answered by: primary · Qwen/Qwen3-4B-Instruct-2507+lora · adapter HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1
- Human review: not required

## r3 (must-have): Working knowledge of Pandas
- Decision: **MISSING** (not_documented); model said MISSING
- Explanation: Requirement "Working knowledge of Pandas": MISSING. No statement in the CV addresses it. This is absence of evidence, not proof that the candidate lacks it.
- Model text: The CV says nothing about this requirement.
- Validator: must_have_absence_of_evidence
- Bias audit: PASS
- NLI judge: not run
- Answered by: primary · Qwen/Qwen3-4B-Instruct-2507+lora · adapter HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1
- Human review: **REQUIRED** — validator:must_have_absence_of_evidence

## r4 (must-have): Microsoft Azure Administrator Associate certification
- Decision: **MISSING** (contradicted); model said MISSING
- Evidence: "Enrolled in a Microsoft Azure Administrator Associate preparation course." (chars 334-407)
- Explanation: Requirement "Microsoft Azure Administrator Associate certification": MISSING. The CV text "Enrolled in a Microsoft Azure Administrator Associate preparation course." shows it is not met. Terminology from: SQL Server, Microsoft Access, Microsoft Visio (knowledge base, not candidate evidence).
- Model text: The CV shows this requirement is not met; the quote is copied from the CV.
- Validator: must_have_contradicted
- Bias audit: PASS
- NLI judge: not run
- Answered by: primary · Qwen/Qwen3-4B-Instruct-2507+lora · adapter HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1
- Human review: **REQUIRED** — validator:must_have_contradicted

## r5 (must-have): Ability to design cloud architecture
- Decision: **MET** (supported); model said MET
- Evidence: "Hired to engineer cloud architecture for a multi-region SaaS product." (chars 145-214)
- Explanation: Requirement "Ability to design cloud architecture": MET. The CV states "Hired to engineer cloud architecture for a multi-region SaaS product.". Terminology from: design cloud architecture, design database in the cloud, plan migration to cloud (knowledge base, not candidate evidence).
- Model text: The CV directly shows this requirement; the quote is copied from the CV.
- Validator: no issue
- Bias audit: PASS
- NLI judge: not run
- Answered by: primary · Qwen/Qwen3-4B-Instruct-2507+lora · adapter HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1
- Human review: not required

## r6 (must-have): Working knowledge of FastAPI
- Decision: **MISSING** (not_documented); model said MISSING
- Explanation: Requirement "Working knowledge of FastAPI": MISSING. No statement in the CV addresses it. This is absence of evidence, not proof that the candidate lacks it.
- Model text: The CV says nothing about this requirement.
- Validator: must_have_absence_of_evidence
- Bias audit: PASS
- NLI judge: not run
- Answered by: primary · Qwen/Qwen3-4B-Instruct-2507+lora · adapter HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1
- Human review: **REQUIRED** — validator:must_have_absence_of_evidence
