"""Profile Agent step 4 prompts: read the ANONYMISED CV into skills / education / experience.

Model: the team's plain Qwen3-4B-Instruct-2507 (the same as job-q1 and the Matcher, no LoRA),
so it adds no GPU memory. Versions are documented in prompts/PROMPT_LIBRARY.md.

profile-q1  written instructions + 2 solved examples (EN experience, FR education/skills),
            one call per group of CV sections, answer = one JSON object.
"""

import json

PROMPT_VERSION = "profile-q1"

SYSTEM_P1 = """You read one part of a CV and copy its facts into JSON.

The CV is anonymised: [NAME], [EMAIL], [PHONE], [URL], [ADDRESS] and [PERSONAL] hide personal data.
Never copy them into a value and never guess what they hide.

Answer with exactly one JSON object, nothing else:
{"skills": [{"name": "...", "evidence": "..."}],
 "education": [{"degree": "...", "field": "...", "institution": "...", "end": "...", "evidence": "..."}],
 "experience": [{"title": "...", "company": "...", "start": "...", "end": "...", "evidence": "..."}]}

Rules:
1. evidence: copy EXACTLY one line of the CV (same words, same spelling, same accents) that shows the item.
   If the item is spread over two lines in a row, copy both lines. Every other value must be written in its evidence.
2. skills: technologies, tools, programming languages, frameworks, methods, certifications and spoken
   languages named in the text. One item per skill: "Python, SQL" gives two items. Keep the CV's spelling.
   Not soft qualities ("passionate"), not job titles, not company or school names.
3. education: one item per degree or diploma. degree = the kind of diploma ("Engineering degree",
   "MSc", "Licence", "Master"); field = the subject ("Computer Science"); institution = the school or
   university; end = the year it ended or will end.
4. experience: one item per job or internship (not personal or academic projects).
   title = the job title; company = the employer.
5. dates: copy them as written ("2021", "06/2020", "mars 2019"). "2019 – 2023" gives start "2019" and
   end "2023"; "2022 - present" or "depuis 2022" gives end "present".
6. A value that is not written in the CV is null. Never invent, never translate.
7. Nothing of a kind in this part: an empty list."""

_EX1_IN = """Section: EXPERIENCE
Backend Developer, Vermeg — Tunis    2021 - present
- Built REST APIs in Java and Spring Boot; deployed with Docker.
Software Engineering Intern, Sofrecom    06/2020 - 09/2020
- [NAME] automated tests with Selenium."""

_EX1_OUT = {
    "skills": [
        {"name": "Java", "evidence": "- Built REST APIs in Java and Spring Boot; deployed with Docker."},
        {"name": "Spring Boot", "evidence": "- Built REST APIs in Java and Spring Boot; deployed with Docker."},
        {"name": "Docker", "evidence": "- Built REST APIs in Java and Spring Boot; deployed with Docker."},
        {"name": "REST APIs", "evidence": "- Built REST APIs in Java and Spring Boot; deployed with Docker."},
        {"name": "Selenium", "evidence": "- [NAME] automated tests with Selenium."},
    ],
    "education": [],
    "experience": [
        {"title": "Backend Developer", "company": "Vermeg", "start": "2021", "end": "present",
         "evidence": "Backend Developer, Vermeg — Tunis    2021 - present"},
        {"title": "Software Engineering Intern", "company": "Sofrecom", "start": "06/2020", "end": "09/2020",
         "evidence": "Software Engineering Intern, Sofrecom    06/2020 - 09/2020"},
    ],
}

_EX2_IN = """Section: FORMATION
Diplôme national d'ingénieur en Informatique — ENIT, 2022
Baccalauréat Mathématiques, Lycée Pilote de Sfax, 2017

Section: COMPÉTENCES
Python, TensorFlow, SQL | Anglais (C1), Français
Soft skills : rigoureux, esprit d'équipe"""

_EX2_OUT = {
    "skills": [
        {"name": "Python", "evidence": "Python, TensorFlow, SQL | Anglais (C1), Français"},
        {"name": "TensorFlow", "evidence": "Python, TensorFlow, SQL | Anglais (C1), Français"},
        {"name": "SQL", "evidence": "Python, TensorFlow, SQL | Anglais (C1), Français"},
        {"name": "Anglais", "evidence": "Python, TensorFlow, SQL | Anglais (C1), Français"},
        {"name": "Français", "evidence": "Python, TensorFlow, SQL | Anglais (C1), Français"},
    ],
    "education": [
        {"degree": "Diplôme national d'ingénieur", "field": "Informatique", "institution": "ENIT", "end": "2022",
         "evidence": "Diplôme national d'ingénieur en Informatique — ENIT, 2022"},
        {"degree": "Baccalauréat", "field": "Mathématiques", "institution": "Lycée Pilote de Sfax", "end": "2017",
         "evidence": "Baccalauréat Mathématiques, Lycée Pilote de Sfax, 2017"},
    ],
    "experience": [],
}

EXAMPLES_P1 = [
    {"input": _EX1_IN, "output": json.dumps(_EX1_OUT, ensure_ascii=False)},
    {"input": _EX2_IN, "output": json.dumps(_EX2_OUT, ensure_ascii=False)},
]

VERSIONS = {"profile-q1": (SYSTEM_P1, EXAMPLES_P1)}


def get_prompt(version: str = PROMPT_VERSION) -> tuple[str, list[dict]]:
    if version not in VERSIONS:
        raise ValueError(f"unknown Profile Agent prompt {version!r}; choose from {sorted(VERSIONS)}")
    return VERSIONS[version]
