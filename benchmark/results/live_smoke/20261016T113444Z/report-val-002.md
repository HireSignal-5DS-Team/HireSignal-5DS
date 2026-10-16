# Matching report — CV `cv-val-002` vs job `job-val-002`

MET 3 · MISSING 1 · UNCERTAIN 0 · must-have met 1/2 · **2 requirement(s) need human review**

_Requirement-level screening aid. No automatic rejection or hiring decision._

Prompt `p1` · knowledge `rag.bm25`

## r1 (nice-have): Working knowledge of FastAPI
- Decision: **MET** (supported); model said MET
- Evidence: "Led the migration of reporting jobs to FastAPI." (chars 236-283)
- Explanation: Requirement "Working knowledge of FastAPI": MET. The CV states "Led the migration of reporting jobs to FastAPI.".
- Model text: The CV directly shows this requirement; the quote is copied from the CV.
- Validator: no issue
- Bias audit: PASS
- NLI judge: not run
- Answered by: primary · Qwen/Qwen3-4B-Instruct-2507+lora · adapter HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1
- Human review: not required

## r2 (nice-have): Working knowledge of database design
- Decision: **MET** (supported); model said MET
- Evidence: "Modelled 40 relational tables with primary keys, foreign keys and indexes for the HR system." (chars 93-185)
- Explanation: Requirement "Working knowledge of database design": MET. The CV states "Modelled 40 relational tables with primary keys, foreign keys and indexes for the HR system.". Terminology from: design database in the cloud, create database diagrams, manage database (knowledge base, not candidate evidence).
- Model text: The CV directly shows this requirement; the quote is copied from the CV.
- Validator: semantic_inference_no_term_in_quote
- Bias audit: PASS
- NLI judge: not run
- Answered by: primary · Qwen/Qwen3-4B-Instruct-2507+lora · adapter HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1
- Human review: **REQUIRED** — validator:semantic_inference_no_term_in_quote

## r3 (must-have): Hands-on Oracle Warehouse Builder experience
- Decision: **MET** (supported); model said MET
- Evidence: "Built OWB mappings for the finance data mart." (chars 188-233)
- Explanation: Requirement "Hands-on Oracle Warehouse Builder experience": MET. The CV states "Built OWB mappings for the finance data mart.". Terminology from: Oracle Warehouse Builder, identify software for warehouse management, Oracle Relational Database (knowledge base, not candidate evidence).
- Model text: The CV directly shows this requirement; the quote is copied from the CV.
- Validator: no issue
- Bias audit: PASS
- NLI judge: not run
- Answered by: primary · Qwen/Qwen3-4B-Instruct-2507+lora · adapter HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1
- Human review: not required

## r4 (must-have): Microsoft Azure Administrator Associate certification
- Decision: **MISSING** (contradicted); model said MISSING
- Evidence: "Enrolled in a Microsoft Azure Administrator Associate preparation course." (chars 356-429)
- Explanation: Requirement "Microsoft Azure Administrator Associate certification": MISSING. The CV text "Enrolled in a Microsoft Azure Administrator Associate preparation course." shows it is not met. Terminology from: SQL Server, Microsoft Access, Microsoft Visio (knowledge base, not candidate evidence).
- Model text: The CV shows this requirement is not met; the quote is copied from the CV.
- Validator: must_have_contradicted
- Bias audit: PASS
- NLI judge: not run
- Answered by: primary · Qwen/Qwen3-4B-Instruct-2507+lora · adapter HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1
- Human review: **REQUIRED** — validator:must_have_contradicted
