# Requirement check: CV `cv-ex-1` vs job `JD-EX-1` (Backend Developer)

> **Decision support only. This report checks job requirements against the text of an anonymised CV. It is not a hiring decision and makes no recommendation about the person. A human reviewer makes every decision, and must check each item flagged for review.**

MET 2 · MISSING 1 · UNCERTAIN 0 · must-have met 2/2 · **2 requirement(s) need human review**

## Summary

3 requirement(s) were checked against the CV: 2 MET, 1 MISSING and 0 UNCERTAIN. 2 of 2 must-have requirement(s) are MET. 2 requirement(s) need human review.

_Written by: deterministic template_

## r1 (must-have): At least 3 years of professional experience with Java

- Decision: **MET** (basis: supported); Matcher model said MET
- Note: MET: the CV states "Backend developer, Acme (2019 - present): Java and Spring Boot services." A human reviewer must check it. _(written by: deterministic template)_
- Explanation: Requirement "At least 3 years of professional experience with Java": MET. The CV states "Backend developer, Acme (2019 - present): Java and Spring Boot services.". The quoted text covers the required 3 years. Terminology from: Java (computer programming) (knowledge base, not candidate evidence). _(deterministic, from validated fields)_
- Evidence (verbatim CV quote, chars 31-103): "Backend developer, Acme (2019 - present): Java and Spring Boot services."
- Knowledge shown to the model (terminology, NOT candidate evidence): Java (computer programming) [http://data.europa.eu/esco/skill/19a8293b-8e95-4de3-983f-77484079c389]
- Validator: no issue
- Bias audit: PASS
- NLI Judge: FAIL (score 0.996) · nli-judge:cross-encoder/nli-deberta-v3-xsmall
- Matcher model: primary · Qwen/Qwen3-4B-Instruct-2507+lora · adapter HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1
- Human review: **REQUIRED**: judge:disagrees

## r2 (must-have): Solid knowledge of SQL databases (PostgreSQL or Oracle)

- Decision: **MET** (basis: supported); Matcher model said MET
- Note: MET: the CV states "Built REST APIs with PostgreSQL." A human reviewer must check it. _(written by: deterministic template)_
- Explanation: Requirement "Solid knowledge of SQL databases (PostgreSQL or Oracle)": MET. The CV states "Built REST APIs with PostgreSQL.". Terminology from: SQL, PostgreSQL (knowledge base, not candidate evidence). _(deterministic, from validated fields)_
- Evidence (verbatim CV quote, chars 106-138): "Built REST APIs with PostgreSQL."
- Knowledge shown to the model (terminology, NOT candidate evidence): SQL [http://data.europa.eu/esco/skill/598de5b0-5b58-4ea7-8058-a4bc4d18c742]; PostgreSQL [http://data.europa.eu/esco/skill/a8d07b5a-c1a1-42c6-9d53-db9c7a2ca996]
- Validator: no issue
- Bias audit: PASS
- NLI Judge: UNCERTAIN (score 0.760) · nli-judge:cross-encoder/nli-deberta-v3-xsmall
- Matcher model: primary · Qwen/Qwen3-4B-Instruct-2507+lora · adapter HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1
- Human review: **REQUIRED**: judge:uncertain

## r3 (nice-have): Experience with Kubernetes is a plus

- Decision: **MISSING** (basis: not_documented); Matcher model said MISSING
- Note: MISSING: the CV does not mention it (absence of evidence, not proof of absence). _(written by: deterministic template)_
- Explanation: Requirement "Experience with Kubernetes is a plus": MISSING. No statement in the CV addresses it. This is absence of evidence, not proof that the candidate lacks it. _(deterministic, from validated fields)_
- Evidence: none quoted
- Validator: no issue
- Bias audit: PASS
- NLI Judge: PASS (score 0.997) · nli-judge:cross-encoder/nli-deberta-v3-xsmall
- Matcher model: primary · Qwen/Qwen3-4B-Instruct-2507+lora · adapter HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1
- Human review: not required

## Provenance

- Report schema 1.0.0, renderer `reporter.deterministic.v1`
- SLM layer: unavailable: HS\_REPORTER\_MODEL\_PATH=/nonexistent.gguf not found
- Text sections: 4 total, 0 written by the SLM, 0 deterministic fallback after a failed fact check
- Matcher prompt `p1` · knowledge `rag.gated.v1+bm25` · judge `nli-judge:cross-encoder/nli-deberta-v3-xsmall`

_Decision support only. This report checks job requirements against the text of an anonymised CV. It is not a hiring decision and makes no recommendation about the person. A human reviewer makes every decision, and must check each item flagged for review._
