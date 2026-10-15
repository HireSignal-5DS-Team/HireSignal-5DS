"""Split CV text into sections (Experience, Education, Skills, ...).

Works for English and French CVs. The split is rule-based on purpose:
headings in CVs are short and predictable, so a model is not needed here,
and rules are easy to explain and test.

The sections are used later by the Match Agent to chunk a CV "by structure".
"""

import re
import unicodedata

# Section name -> heading words that announce it (lowercase, no accents).
SECTION_KEYWORDS = {
    # Personal data: the Profile Agent anonymises "header" and "contact".
    "contact": [
        "contact", "contacts", "contact information", "contact details",
        "personal information", "personal details", "personal info",
        "coordonnees", "informations personnelles", "infos personnelles",
    ],
    "summary": [
        "summary", "profile", "professional summary", "about me", "objective",
        "career objective", "profil", "resume", "a propos", "objectif",
    ],
    "experience": [
        "experience", "experiences", "work experience", "professional experience",
        "employment", "employment history", "work history", "internships", "internship",
        "experience professionnelle", "experiences professionnelles", "stages", "stage",
        "parcours professionnel",
    ],
    "education": [
        "education", "academic background", "academic background and education",
        "qualifications", "formation", "formations", "parcours academique",
        "diplomes", "etudes", "cursus",
    ],
    "skills": [
        "skills", "technical skills", "key skills", "core skills", "competencies",
        "hard skills", "soft skills", "technologies", "tools", "competences",
        "competences techniques", "outils",
    ],
    "projects": [
        "projects", "academic projects", "personal projects", "key projects",
        "projets", "projets academiques", "projets personnels", "realisations",
    ],
    "certifications": [
        "certifications", "certificates", "licenses", "awards", "achievements",
        "certificats", "prix", "distinctions",
    ],
    "languages": ["languages", "language skills", "langues", "langues parlees"],
    "interests": [
        "interests", "hobbies", "activities", "extracurricular activities",
        "volunteering", "centres d'interet", "loisirs", "activites", "vie associative",
    ],
}

# Reverse lookup: heading text -> section name.
_HEADING_TO_SECTION = {
    kw: section for section, kws in SECTION_KEYWORDS.items() for kw in kws
}

MAX_HEADING_LEN = 45  # real headings are short lines


def _normalise(line: str) -> str:
    """Lowercase, strip accents, punctuation and decorations: 'EXPÉRIENCE :' -> 'experience'."""
    line = unicodedata.normalize("NFKD", line)
    line = "".join(c for c in line if not unicodedata.combining(c))
    line = line.lower()
    line = re.sub(r"[^a-z' ]+", " ", line)  # drop digits, dashes, colons, icons
    return re.sub(r"\s+", " ", line).strip()


def detect_heading(line: str) -> str | None:
    """Return the section name if this line is a section heading, else None."""
    if not line or len(line) > MAX_HEADING_LEN:
        return None
    return _HEADING_TO_SECTION.get(_normalise(line))


def split_sections(text: str) -> dict[str, str]:
    """Split text into {section_name: section_text}.

    - Text before the first heading goes to "header" (name, contact details).
      The Profile Agent anonymises this part.
    - If the same section appears twice (e.g. two-column CVs), texts are joined.
    """
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in text.splitlines():
        section = detect_heading(line)
        if section:
            current = section
            sections.setdefault(current, [])
        else:
            sections[current].append(line)

    return {
        name: "\n".join(lines).strip()
        for name, lines in sections.items()
        if "\n".join(lines).strip()
    }
