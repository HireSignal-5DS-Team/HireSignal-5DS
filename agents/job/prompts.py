"""NuExtract template and in-context examples for the Job Agent (versioned).

NuExtract is not a chat model: its "prompt" is
  1. a JSON template (the empty form, with a type for every field), and
  2. a few solved examples (input -> output).
Every version is kept here and documented in prompts/PROMPT_LIBRARY.md
(role, technique, observed failures, fix), as the course requires.

Template types (NuExtract 2.0 model card):
  "verbatim-string"  copy text exactly as it appears in the input
  "string"           free text (may paraphrase)
  "number"           a number
  [...options]       enum: one of the listed values
  ["string"]         array of strings
"""

import json

PROMPT_VERSION = "job-v1"

CATEGORIES = ["skill", "experience", "education", "certification", "language", "other"]

# ------------------------------------------------------------------ v1 ---
# Technique: structured output (typed template) + few-shot (2 examples).
# The examples teach the two habits the template alone cannot express:
#   - one requirement per skill ("Java and Spring Boot" -> 2 items, same evidence);
#   - must vs nice from the wording ("a plus", "preferred" -> nice).

TEMPLATE_V1 = {
    "title": "verbatim-string",
    "requirements": [
        {
            "text": "string",
            "evidence": "verbatim-string",
            "kind": ["must", "nice"],
            "category": CATEGORIES,
            "skill_terms": ["string"],
            "min_years": "number",
        }
    ],
}

_EX1_INPUT = """Data Engineer

What you need:
- 2+ years of experience with Python and Airflow.
- Bachelor's degree in computer science or a related field.
- Good command of English.

Bonus points:
- Experience with Spark is a plus.
- GCP certification preferred."""

_EX1_OUTPUT = {
    "title": "Data Engineer",
    "requirements": [
        {"text": "2+ years of experience with Python",
         "evidence": "2+ years of experience with Python and Airflow.",
         "kind": "must", "category": "experience", "skill_terms": ["Python"], "min_years": 2},
        {"text": "2+ years of experience with Airflow",
         "evidence": "2+ years of experience with Python and Airflow.",
         "kind": "must", "category": "experience", "skill_terms": ["Airflow"], "min_years": 2},
        {"text": "Bachelor's degree in computer science or a related field",
         "evidence": "Bachelor's degree in computer science or a related field.",
         "kind": "must", "category": "education", "skill_terms": [], "min_years": None},
        {"text": "Good command of English",
         "evidence": "Good command of English.",
         "kind": "must", "category": "language", "skill_terms": ["English"], "min_years": None},
        {"text": "Experience with Spark",
         "evidence": "Experience with Spark is a plus.",
         "kind": "nice", "category": "skill", "skill_terms": ["Spark"], "min_years": None},
        {"text": "GCP certification",
         "evidence": "GCP certification preferred.",
         "kind": "nice", "category": "certification", "skill_terms": ["GCP"], "min_years": None},
    ],
}

_EX2_INPUT = """Développeur Full Stack (H/F) - Sfax

Profil recherché :
- Diplôme d'ingénieur en informatique.
- Minimum 3 ans d'expérience en développement web avec Angular.
- Maîtrise de SQL.
- La connaissance de Docker serait un atout."""

_EX2_OUTPUT = {
    "title": "Développeur Full Stack (H/F)",
    "requirements": [
        {"text": "Diplôme d'ingénieur en informatique",
         "evidence": "Diplôme d'ingénieur en informatique.",
         "kind": "must", "category": "education", "skill_terms": [], "min_years": None},
        {"text": "Minimum 3 ans d'expérience en développement web avec Angular",
         "evidence": "Minimum 3 ans d'expérience en développement web avec Angular.",
         "kind": "must", "category": "experience", "skill_terms": ["Angular"], "min_years": 3},
        {"text": "Maîtrise de SQL",
         "evidence": "Maîtrise de SQL.",
         "kind": "must", "category": "skill", "skill_terms": ["SQL"], "min_years": None},
        {"text": "Connaissance de Docker",
         "evidence": "La connaissance de Docker serait un atout.",
         "kind": "nice", "category": "skill", "skill_terms": ["Docker"], "min_years": None},
    ],
}

EXAMPLES_V1 = [
    {"input": _EX1_INPUT, "output": json.dumps(_EX1_OUTPUT, ensure_ascii=False)},
    {"input": _EX2_INPUT, "output": json.dumps(_EX2_OUTPUT, ensure_ascii=False)},
]

# Active version used by the agent.
TEMPLATE = TEMPLATE_V1
EXAMPLES = EXAMPLES_V1


def template_json() -> str:
    """Template as the indented JSON string NuExtract expects."""
    return json.dumps(TEMPLATE, indent=4, ensure_ascii=False)
