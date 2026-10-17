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

# ------------------------------------------------------------------ v2 ---
# Fix for failure F1 (v1): "Java and Spring Boot" gave one item with
# skill_terms ["Java"]; Spring Boot was lost. The v1 examples always showed one
# skill per item, so the model learned "one term per item" and stopped early.
#
# Technique: task decomposition. The model does the easy part (one item per
# requirement LINE, listing EVERY skill of that line); code does the exact part
# (validate.split_compound makes one requirement per skill for "and"/"et",
# keeps alternatives "or"/"ou" together).
# Also: `evidence` comes first in the template, so the model copies the line
# before describing it (the description is then grounded in the quote).

TEMPLATE_V2 = {
    "title": "verbatim-string",
    "requirements": [
        {
            "evidence": "verbatim-string",
            "skill_terms": ["verbatim-string"],
            "kind": ["must", "nice"],
            "category": CATEGORIES,
            "min_years": "number",
            "text": "string",
        }
    ],
}

_V2_EX1_INPUT = """Data Engineer

What you need:
- 2+ years of experience with Python, Airflow and dbt.
- Experience with AWS or Azure.
- Bachelor's degree in computer science or a related field.
- Good command of English and French.

Bonus points:
- Knowledge of Spark and Kafka is a plus.
- GCP certification preferred."""

_V2_EX1_OUTPUT = {
    "title": "Data Engineer",
    "requirements": [
        {"evidence": "2+ years of experience with Python, Airflow and dbt.",
         "skill_terms": ["Python", "Airflow", "dbt"],
         "kind": "must", "category": "experience", "min_years": 2,
         "text": "2+ years of experience with Python, Airflow and dbt"},
        {"evidence": "Experience with AWS or Azure.",
         "skill_terms": ["AWS", "Azure"],
         "kind": "must", "category": "skill", "min_years": None,
         "text": "Experience with AWS or Azure"},
        {"evidence": "Bachelor's degree in computer science or a related field.",
         "skill_terms": [],
         "kind": "must", "category": "education", "min_years": None,
         "text": "Bachelor's degree in computer science or a related field"},
        {"evidence": "Good command of English and French.",
         "skill_terms": ["English", "French"],
         "kind": "must", "category": "language", "min_years": None,
         "text": "Good command of English and French"},
        {"evidence": "Knowledge of Spark and Kafka is a plus.",
         "skill_terms": ["Spark", "Kafka"],
         "kind": "nice", "category": "skill", "min_years": None,
         "text": "Knowledge of Spark and Kafka"},
        {"evidence": "GCP certification preferred.",
         "skill_terms": ["GCP"],
         "kind": "nice", "category": "certification", "min_years": None,
         "text": "GCP certification"},
    ],
}

_V2_EX2_INPUT = """Développeur Full Stack (H/F) - Sfax

Profil recherché :
- Diplôme d'ingénieur en informatique.
- Minimum 3 ans d'expérience avec Angular et Node.js.
- Maîtrise de MySQL ou PostgreSQL.
- La connaissance de Docker serait un atout."""

_V2_EX2_OUTPUT = {
    "title": "Développeur Full Stack (H/F)",
    "requirements": [
        {"evidence": "Diplôme d'ingénieur en informatique.",
         "skill_terms": [],
         "kind": "must", "category": "education", "min_years": None,
         "text": "Diplôme d'ingénieur en informatique"},
        {"evidence": "Minimum 3 ans d'expérience avec Angular et Node.js.",
         "skill_terms": ["Angular", "Node.js"],
         "kind": "must", "category": "experience", "min_years": 3,
         "text": "Minimum 3 ans d'expérience avec Angular et Node.js"},
        {"evidence": "Maîtrise de MySQL ou PostgreSQL.",
         "skill_terms": ["MySQL", "PostgreSQL"],
         "kind": "must", "category": "skill", "min_years": None,
         "text": "Maîtrise de MySQL ou PostgreSQL"},
        {"evidence": "La connaissance de Docker serait un atout.",
         "skill_terms": ["Docker"],
         "kind": "nice", "category": "skill", "min_years": None,
         "text": "Connaissance de Docker"},
    ],
}

EXAMPLES_V2 = [
    {"input": _V2_EX1_INPUT, "output": json.dumps(_V2_EX1_OUTPUT, ensure_ascii=False)},
    {"input": _V2_EX2_INPUT, "output": json.dumps(_V2_EX2_OUTPUT, ensure_ascii=False)},
]

# ------------------------------------------------------------------ v3 ---
# Fix for the first real evaluation (10 USAJOBS offers, F1 0.22 / 0.17):
#   E1 answers cut off on long offers (broken JSON, card lost),
#   E2 the model extracted every "must" sentence: citizenship, probation,
#      transcripts, "maximum 2-page resume", direct deposit...,
#   E3 invented categories ("condition", "qualification", "age").
# Techniques:
#   - input selection + chunking (agents/job/sections.py): only requirement
#     sections are sent, ~700 characters per call, so answers stay short (E1)
#     and most administrative text never reaches the model (E2);
#   - negative examples: the examples now CONTAIN text to skip (administrative
#     conditions, application instructions, boilerplate) and their outputs leave
#     it out, plus one example whose correct output is empty (E2). NuExtract takes
#     no instructions, so "what not to extract" can only be taught by example;
#   - every example uses only the allowed categories (E3); invalid ones are also
#     re-inferred by code (validate.infer_category).
# The template has no title: the title comes from a separate small call.

TEMPLATE_V3 = {
    "requirements": [
        {
            "evidence": "verbatim-string",
            "skill_terms": ["verbatim-string"],
            "kind": ["must", "nice"],
            "category": CATEGORIES,
            "min_years": "number",
            "text": "string",
        }
    ],
}

TITLE_TEMPLATE = {"job_title": "verbatim-string"}


def _v3(ev, terms, kind, cat, years, text):
    return {"evidence": ev, "skill_terms": terms, "kind": kind, "category": cat,
            "min_years": years, "text": text}


_V3_EX1_INPUT = (
    "Basic Requirement: Bachelor's degree in statistics, mathematics or computer science. "
    "You must have one year of specialized experience equivalent to the GS-11 level. "
    "Experience refers to paid and unpaid experience, including volunteer work. "
    "Transcripts must be submitted with your application. "
    "Preferred Qualifications: Experience with Python and SQL. Knowledge of Tableau is a plus."
)
_V3_EX1_OUTPUT = {"requirements": [
    _v3("Bachelor's degree in statistics, mathematics or computer science.", [], "must", "education", None,
        "Bachelor's degree in statistics, mathematics or computer science"),
    _v3("You must have one year of specialized experience equivalent to the GS-11 level.", [], "must",
        "experience", 1, "One year of specialized experience equivalent to the GS-11 level"),
    _v3("Experience with Python and SQL.", ["Python", "SQL"], "nice", "experience", None,
        "Experience with Python and SQL"),
    _v3("Knowledge of Tableau is a plus.", ["Tableau"], "nice", "skill", None, "Knowledge of Tableau"),
]}

_V3_EX2_INPUT = (
    "You must be a U.S. Citizen. A background investigation is required. "
    "A one-year probationary period may be required. Maximum of 2-page resume. "
    "Males born after 12/31/1959 must be registered with the Selective Service. "
    "Federal salary payments are made by direct deposit."
)
_V3_EX2_OUTPUT = {"requirements": []}

_V3_EX3_INPUT = """Profil recherché :
- Diplôme d'ingénieur en informatique.
- Minimum 3 ans d'expérience avec Angular et Node.js.
- Maîtrise de MySQL ou PostgreSQL.
- Poste basé à Tunis, télétravail partiel possible.
- Merci d'envoyer votre CV avant le 30 novembre.
- La connaissance de Docker serait un atout."""
_V3_EX3_OUTPUT = {"requirements": [
    _v3("Diplôme d'ingénieur en informatique.", [], "must", "education", None, "Diplôme d'ingénieur en informatique"),
    _v3("Minimum 3 ans d'expérience avec Angular et Node.js.", ["Angular", "Node.js"], "must", "experience", 3,
        "Minimum 3 ans d'expérience avec Angular et Node.js"),
    _v3("Maîtrise de MySQL ou PostgreSQL.", ["MySQL", "PostgreSQL"], "must", "skill", None,
        "Maîtrise de MySQL ou PostgreSQL"),
    _v3("La connaissance de Docker serait un atout.", ["Docker"], "nice", "skill", None, "Connaissance de Docker"),
]}

EXAMPLES_V3 = [
    {"input": _V3_EX1_INPUT, "output": json.dumps(_V3_EX1_OUTPUT, ensure_ascii=False)},
    {"input": _V3_EX2_INPUT, "output": json.dumps(_V3_EX2_OUTPUT, ensure_ascii=False)},
    {"input": _V3_EX3_INPUT, "output": json.dumps(_V3_EX3_OUTPUT, ensure_ascii=False)},
]

# ------------------------------------------------------------------ v4 ---
# Fix for the v2-vs-v3 evaluation: the model fills skill_terms on 1 of 151 items,
# so compound lines are never split and most items share no term with the gold.
# Re-scoring the saved v3 cards with the right terms on the same sentences:
# 21 -> 59 correct requirements.
# Technique: task decomposition again. job-v4 = job-v3 for finding the sentences,
# then a SECOND, focused call per requirement sentence with a one-field template
# that only asks for the skill names. The sentence is short, so the model has one
# job. Examples include sentences whose correct answer is empty (degree, years of
# experience, duties-style lists), because a probe showed the model listing
# activities ("Writing", "testing") as skills.

TERMS_TEMPLATE = {"skill_terms": ["verbatim-string"]}


def _terms(text, terms):
    return {"input": text, "output": json.dumps({"skill_terms": terms}, ensure_ascii=False)}


TERMS_EXAMPLES = [
    _terms("2+ years of experience with Python, Airflow and dbt.", ["Python", "Airflow", "dbt"]),
    _terms("Knowledge of statistical modeling and machine learning techniques.",
           ["statistical modeling", "machine learning"]),
    _terms("Maîtrise de MySQL ou PostgreSQL.", ["MySQL", "PostgreSQL"]),
    _terms("Bachelor's degree in computer science or a related field.", []),
    _terms("One year of specialized experience equivalent to the GS-09 level.", []),
    _terms("Preparing reports, briefing senior managers, and coordinating with other teams.", []),
]

# ------------------------------------------------------------------ q1 ---
# job-q1: the team's plain Qwen3-4B-Instruct (no LoRA) instead of NuExtract.
# Why: GPU memory. The Matcher already runs Qwen3-4B (config/matcher_models.json);
# on a 4 GB card NuExtract (~1.9 GB) and Qwen (~2.5-3.5 GB) cannot both stay loaded.
# Sharing the Matcher's plain-Qwen server (or the same hosted API) adds no memory.
# What changes: Qwen follows written instructions, so the prompt is a role + explicit
# rules (what to extract, what to skip, the skill-name rules S1-S6 of
# eval/job_agent/ANNOTATION_RULES.md, the JSON format) + the job-v3 examples as
# few-shot turns. Skill names are asked in the SAME call (no second call per
# sentence as in job-v4): fewer calls on a server shared with the Matcher.
# Unchanged: requirement sections, chunks, guardrails, not-a-requirement filter.

SYSTEM_Q1 = """You are the Job Agent of HireSignal, a CV-screening system. You read a PIECE of a job offer \
and list the requirements a CANDIDATE must meet. A recruiter and a matching system rely on your list, \
and code checks every quote against the offer, so never invent or reword a quote.

Answer with a JSON object only: {"requirements": [ ... ]}. Each item has these keys, in this order:
- "evidence": the requirement sentence or clause, copied EXACTLY, character for character, from the input.
- "skill_terms": the named skills the requirement asks for, each copied exactly from the evidence: tools, \
technologies, languages, methods, domains (e.g. "Python", "machine learning", "SQL"). After "such as", \
"e.g.", "including" or "particularly", list each named example. Use the short form a CV would use \
("CI/CD", not "CI/CD pipelines"). A full name with its acronym in brackets is one term, the first form \
written. Never terms: verbs or activities, adjectives, generic words (data, code, applications, solutions, \
environments), grade levels (GS-13), generic labels ("specialized experience", "IT-related experience"). \
Education items have no terms: []. A soft skill is a term only when it stands alone as a named competency.
- "kind": "nice" when the wording or its heading makes it optional (preferred, desired, a plus, nice to \
have, ideally, appreciated, atout, souhaité); otherwise "must".
- "category": exactly one of "skill", "experience", "education", "certification", "language", "other".
- "min_years": the minimum number of years asked for, as a number (52 weeks = 1), or null if none is stated.
- "text": the requirement as one short statement.

Extract ONLY what the candidate must have: degrees, experience, skills, knowledge, certifications, \
languages, named competencies. Do NOT extract:
- job duties or responsibilities (what the job does);
- citizenship, residency, age, background checks, drug tests, security clearance, Selective Service, \
probation, time in grade, merit promotion rules;
- application instructions: resume length or content, transcripts, questionnaires, deadlines, links, \
how or where to apply, foreign-education evaluation;
- definitions and explanations ("Experience refers to ...", "One year of graduate education is ...");
- salary, benefits, location, schedule.
When the text gives alternative ways to qualify ("... OR a Ph.D. OR a combination of education and \
experience"), extract only the first one. If the piece contains no requirement, answer {"requirements": []}."""

EXAMPLES_Q1 = EXAMPLES_V3  # same chunk-sized examples (one is all text to skip, with an empty answer)

# ------------------------------------------------------------ registry ---

VERSIONS = {
    "job-v1": (TEMPLATE_V1, EXAMPLES_V1),
    "job-v2": (TEMPLATE_V2, EXAMPLES_V2),
    "job-v3": (TEMPLATE_V3, EXAMPLES_V3),
    "job-v4": (TEMPLATE_V3, EXAMPLES_V3),
    "job-q1": (SYSTEM_Q1, EXAMPLES_Q1),
}
# Which model a version is written for (agents/job/backend.make_backend picks the client).
MODEL_FAMILY = {"job-v1": "nuextract", "job-v2": "nuextract", "job-v3": "nuextract", "job-v4": "nuextract",
                "job-q1": "qwen"}
# How the offer is given to the model: the whole offer in one call, or only the
# requirement sections, a chunk per call (agents/job/sections.py).
STRATEGY = {"job-v1": "whole", "job-v2": "whole", "job-v3": "sections", "job-v4": "sections",
            "job-q1": "sections"}
# Versions that ask for the skill names in a second call per requirement sentence.
TERMS_PASS = {"job-v4"}
PROMPT_VERSION = "job-v4"  # active version: best measured on the 10 real offers (PROMPT_LIBRARY.md, run 3)


def get_prompt(version: str | None = None) -> tuple[str, list[dict]]:
    """(template as indented JSON, or the instructions for a chat model; examples) for a prompt version."""
    template, examples = VERSIONS[version or PROMPT_VERSION]
    if isinstance(template, str):  # written instructions (job-q1)
        return template, examples
    return json.dumps(template, indent=4, ensure_ascii=False), examples


def template_json(version: str | None = None) -> str:
    return get_prompt(version)[0]


def title_template() -> str:
    return json.dumps(TITLE_TEMPLATE, indent=4)


def terms_template() -> str:
    return json.dumps(TERMS_TEMPLATE, indent=4)
