# Adapted from team V2: agents/job/sections.py (feature/agent-integration @ a5a03ff)
"""Find the requirement parts of a job offer and cut them into small chunks.

Why (evaluation on 10 real offers, job-v1/v2): sending the whole offer to a 2B model
  - made answers so long they were cut off (broken JSON, card lost), and
  - made the model extract everything that sounds required: citizenship, probation,
    "maximum 2-page resume", direct deposit...
So the agent now sends only the requirement sections, a few sentences at a time.
Rule-based on purpose: headings in job offers are short and predictable.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Sections whose content describes what the candidate must have.
REQUIREMENT_HEADINGS = [
    "requirements", "requirement", "qualifications", "qualification", "minimum qualifications",
    "basic qualifications", "required qualifications", "basic requirements", "minimum requirements",
    "skills", "required skills", "key skills", "technical skills", "skills and experience",
    "what you need", "what you will need", "what you'll need", "what we are looking for",
    "what we're looking for", "who you are", "your profile", "profile", "about you", "you have",
    "must have", "must haves", "experience", "education", "education and experience",
    "profil", "profil recherche", "votre profil", "competences", "competences requises",
    "exigences", "qualifications requises", "prerequis", "formation", "connaissances",
]
# Sections that only add optional requirements: items found there are "nice".
NICE_HEADINGS = [
    "nice to have", "nice to haves", "preferred qualifications", "preferred", "bonus", "bonus points",
    "desired qualifications", "desirable", "pluses", "plus", "a plus", "good to have",
    "atouts", "serait un plus", "un plus", "souhaite", "competences appreciees",
]
# Sections that never contain requirements.
SKIP_HEADINGS = [
    "summary", "duties", "responsibilities", "key responsibilities", "what you will do",
    "what you'll do", "the role", "about the role", "about us", "who we are", "about the company",
    "benefits", "perks", "what we offer", "we offer", "salary", "compensation", "location",
    "conditions of employment", "how to apply", "additional information", "required documents",
    "how you will be evaluated", "next steps", "help", "missions", "vos missions", "description du poste",
    "le poste", "a propos", "qui sommes nous", "avantages", "nous offrons", "remuneration",
    "candidature", "comment postuler",
]

# Inside a kept section: boilerplate starts here (e.g. USAJOBS pastes "Additional information ..."
# into the Qualifications paragraph). Everything after the first marker is dropped.
INLINE_STOP = re.compile(
    r"\b(Additional information|Expand Hide additional information|How You Will Be Evaluated|"
    r"Click the following link to view the occupational questionnaire)\b"
)

CHUNK_CHARS = 700        # ~175 tokens of input per call: answers stay short
MAX_HEADING_CHARS = 60


@dataclass
class Section:
    heading: str
    text: str
    kind_hint: str | None  # "nice" for Nice-to-have sections, else None


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[*#_•\-–—:]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def heading_type(line: str) -> str | None:
    """'requirement', 'nice', 'skip', or None if the line is not a known heading."""
    if not line.strip() or len(line.strip()) > MAX_HEADING_CHARS:
        return None
    norm = _norm(line)
    for kind, names in (("nice", NICE_HEADINGS), ("skip", SKIP_HEADINGS), ("requirement", REQUIREMENT_HEADINGS)):
        if norm in names:
            return kind
    return None


def requirement_sections(post: str) -> list[Section]:
    """The parts of the offer that state requirements, in order."""
    sections, current, kind, lines = [], "", None, []

    def flush():
        text = "\n".join(lines).strip()
        if text and kind in ("requirement", "nice"):
            stop = INLINE_STOP.search(text)
            text = text[:stop.start()].strip() if stop else text
            if text:
                sections.append(Section(current, text, "nice" if kind == "nice" else None))

    for line in post.splitlines():
        found = heading_type(line)
        if found:
            flush()
            current, kind, lines = line.strip(), found, []
        else:
            lines.append(line)
    flush()
    return sections


def _units(text: str) -> list[str]:
    """Lines, and sentences of long lines, as the smallest pieces a chunk is made of."""
    units = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) <= CHUNK_CHARS:
            units.append(line)
        else:  # a long paragraph: cut at sentence ends ("; " or ". " followed by a capital/digit)
            units += [s for s in re.split(r"(?<=[.;])\s+(?=[A-Z0-9(])", line) if s.strip()]
    return units


def chunk_sections(sections: list[Section]) -> list[tuple[str, Section]]:
    """Small pieces of text (with the section they come from), each sent in its own call."""
    chunks = []
    for section in sections:
        current = ""
        for unit in _units(section.text):
            if current and len(current) + len(unit) + 1 > CHUNK_CHARS:
                chunks.append((current, section))
                current = ""
            current = f"{current}\n{unit}" if current else unit
        if current:
            chunks.append((current, section))
    return chunks
