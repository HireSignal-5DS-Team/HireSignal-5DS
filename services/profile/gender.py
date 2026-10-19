"""Gendered words in running text -> neutral forms (Decision 17; V2 only hid gender words in the CV header,
agents/profile/detect.py:244).

- pronouns (EN he/she/him/her/his/hers/himself/herself, FR il/elle)  -> "[PRONOUN]"
- honorifics (Mr, Mrs, Ms, Miss, Mx, Mme, Mlle, Madame, Monsieur, Mademoiselle) -> "[PERSONAL]"
- gendered job / role words -> one epicene form for both genders, so the role stays readable for the Matcher:
  FR "Ingénieure" and "Ingénieur" -> "Ingénieur·e"; EN "chairwoman" and "chairman" -> "chairperson".

Whole words only (no letter, digit or _ touching the match: "HER2", "his_id" stay), case-insensitive, accents optional
("ingenieure" too). Exception: honorifics are matched case-sensitively, so "MS SQL Server" / "MS Office" stay.
"""
import re

from .detect import fold

PRONOUNS = ["he", "she", "him", "her", "his", "hers", "himself", "herself", "il", "elle"]
HONORIFICS = ["Mr", "Mrs", "Ms", "Miss", "Mx", "Mme", "Mlle", "Madame", "Monsieur", "Mademoiselle"]

# FR: (masculine, feminine, neutral). Masculine forms that are also English words (consultant, assistant,
# commercial) are left out: only their feminine form is replaced.
_FR = [("ingenieur", "ingenieure", "ingénieur·e"), ("developpeur", "developpeuse", "développeur·se"),
       ("directeur", "directrice", "directeur·rice"), ("etudiant", "etudiante", "étudiant·e"),
       (None, "consultante", "consultant·e"), (None, "assistante", "assistant·e"),
       (None, "commerciale", "commercial·e"), ("technicien", "technicienne", "technicien·ne"),
       ("administrateur", "administratrice", "administrateur·rice"), ("chercheur", "chercheuse", "chercheur·se"),
       ("informaticien", "informaticienne", "informaticien·ne"), ("programmeur", "programmeuse", "programmeur·se"),
       ("concepteur", "conceptrice", "concepteur·rice"), ("docteur", "docteure", "docteur·e"),
       ("enseignant", "enseignante", "enseignant·e"), ("formateur", "formatrice", "formateur·rice"),
       ("vendeur", "vendeuse", "vendeur·se"), ("employe", "employee", "employé·e")]
_EN = {"chairman": "chairperson", "chairwoman": "chairperson", "businessman": "businessperson",
       "businesswoman": "businessperson", "salesman": "salesperson", "saleswoman": "salesperson",
       "spokesman": "spokesperson", "spokeswoman": "spokesperson", "foreman": "supervisor",
       "forewoman": "supervisor", "craftsman": "craftsperson", "craftswoman": "craftsperson",
       "policeman": "police officer", "policewoman": "police officer", "waiter": "server",
       "waitress": "server", "actress": "actor", "stewardess": "flight attendant",
       "headmaster": "head teacher", "headmistress": "head teacher"}
# not "steward": "data steward" is a neutral data role. "employee" is an English word: the FR feminine "employée" is only replaced when written with its accent
_ACCENT_ONLY = {"employee": "employée"}

ROLE_WORDS = {w: neutral for m, f, neutral in _FR for w in (m, f) if w} | _EN

_PRONOUN_RE = re.compile(r"(?<!\w)(?:" + "|".join(PRONOUNS) + r")(?!\w)")
_ROLE_RE = re.compile(r"(?<!\w)(?:" + "|".join(sorted(ROLE_WORDS, key=len, reverse=True)) + r")(?!\w)")
_HONORIFIC_RE = re.compile(r"(?<!\w)(?:" + "|".join(HONORIFICS) + r")\b\.?")


def _same_case(original: str, neutral: str) -> str:
    if original.isupper() and len(original) > 1:
        return neutral.upper()
    return neutral[:1].upper() + neutral[1:] if original[:1].isupper() else neutral


def neutralise_gender(text: str) -> tuple[str, dict[str, int]]:
    """(text with gendered words replaced, counts {'[PRONOUN]': n, '[PERSONAL]': n, 'neutral role words': n})."""
    folded = fold(text)  # same length as text, so offsets are shared
    edits = []  # (start, end, replacement, count key)
    for m in _PRONOUN_RE.finditer(folded):
        edits.append((m.start(), m.end(), "[PRONOUN]", "[PRONOUN]"))
    for m in _ROLE_RE.finditer(folded):
        word = text[m.start():m.end()]
        if m.group(0) in _ACCENT_ONLY and word.lower() != _ACCENT_ONLY[m.group(0)]:
            continue
        edits.append((m.start(), m.end(), _same_case(word, ROLE_WORDS[m.group(0)]), "neutral role words"))
    for m in _HONORIFIC_RE.finditer(text):
        edits.append((m.start(), m.end(), "[PERSONAL]", "[PERSONAL]"))
    out, pos, counts = [], 0, {}
    for s, e, rep, key in sorted(edits):
        if s < pos:
            continue
        out += [text[pos:s], rep]
        pos = e
        counts[key] = counts.get(key, 0) + 1
    out.append(text[pos:])
    return "".join(out), counts
