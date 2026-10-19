# Adapted from team V2: agents/profile/detect.py (feature/agent-integration @ a5a03ff)
"""Step 1 of the Profile Agent: find the candidate's identity in the Reader text.

Rule-based detectors, always on (fast, explainable, no model):
- contact data: email, phone, URL / LinkedIn / GitHub / social handle, address;
- bias proxies (hidden as [PERSONAL]): date of birth, age, gender, honorific
  (Mr / Mme ...), nationality, marital status, place of birth, religion;
- the candidate's name: a "Name:" label, else the CV header (the lines before the
  first section heading), else the words of the email address.

Optional NER models (agents/profile/ner.py) add more spans, e.g. people's names
in a references section. Every detector returns `Span`s on the ORIGINAL text.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

# kind -> placeholder written in the anonymised text
PLACEHOLDER = {
    "NAME": "[NAME]", "EMAIL": "[EMAIL]", "PHONE": "[PHONE]", "URL": "[URL]", "ADDRESS": "[ADDRESS]",
    "DOB": "[PERSONAL]", "AGE": "[PERSONAL]", "GENDER": "[PERSONAL]", "HONORIFIC": "[PERSONAL]",
    "NATIONALITY": "[PERSONAL]", "MARITAL": "[PERSONAL]", "BIRTHPLACE": "[PERSONAL]", "RELIGION": "[PERSONAL]",
}
# when two spans overlap, the higher one wins (then the longer one)
PRIORITY = {"EMAIL": 9, "URL": 8, "PHONE": 7, "DOB": 6, "ADDRESS": 5, "NAME": 4}


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    kind: str          # a key of PLACEHOLDER
    text: str
    source: str        # "regex", "label", "header", "email", "resume-ner", "gliner", "variant", "leak-check"
    score: float = 1.0


# ------------------------------------------------------------------ folding ---

@lru_cache(maxsize=4096)
def _fold_char(c: str) -> str:
    base = unicodedata.normalize("NFD", c)[0]
    low = base.lower()
    return low if len(low) == 1 else c


def fold(text: str) -> str:
    """Lowercase, no accents, SAME LENGTH as the input (so offsets stay valid): 'Éloïse' -> 'eloise'."""
    return "".join(_fold_char(c) for c in text)


# ------------------------------------------------------------------ headings ---
# Short copy of the Reader's heading words (agents/reader/sections.py), so this
# module works on its own; only used to find where the CV header ends.
HEADINGS = {
    "contact", "contacts", "contact information", "contact details", "personal information",
    "personal details", "coordonnees", "informations personnelles",
    "summary", "profile", "professional summary", "about me", "objective", "profil", "resume",
    "a propos", "objectif", "experience", "experiences", "work experience", "professional experience",
    "employment", "employment history", "work history", "internships", "internship",
    "experience professionnelle", "experiences professionnelles", "stages", "stage",
    "education", "academic background", "qualifications", "formation", "formations",
    "parcours academique", "diplomes", "etudes", "cursus", "skills", "technical skills", "key skills",
    "competencies", "competences", "competences techniques", "projects", "academic projects",
    "projets", "certifications", "certificates", "awards", "languages", "langues", "interests",
    "hobbies", "loisirs", "centres d'interet", "references", "referees", "references professionnelles",
}

# Words that are never part of a person's name in a CV header (folded).
NOT_NAME = HEADINGS | {
    "curriculum", "vitae", "cv", "resume", "engineer", "engineering", "developer", "developpeur", "developpeuse",
    "data", "scientist", "science", "software", "student", "etudiant", "etudiante", "ingenieur", "ingenieure",
    "manager", "analyst", "analyste", "intern", "stagiaire", "senior", "junior", "full", "stack", "web",
    "machine", "learning", "deep", "ai", "ia", "designer", "consultant", "consultante", "architect", "devops",
    "cloud", "mobile", "frontend", "backend", "front", "end", "back", "lead", "chef", "projet", "project",
    "product", "owner", "research", "researcher", "assistant", "technician", "technicien", "teacher",
    "professor", "nurse", "accountant", "comptable", "marketing", "sales", "commercial", "commerciale",
    "business", "specialist", "expert", "administrator", "administrateur", "officer", "director",
    "directeur", "directrice", "head", "of", "and", "et", "en", "the", "phd", "msc", "bsc", "master",
    "licence", "bachelor", "doctor", "mobile", "phone", "email", "e-mail", "tel", "address", "adresse",
    "linkedin", "github", "portfolio", "website", "page", "street", "avenue", "rue", "road", "tunisia",
    "tunisie", "france", "paris", "tunis", "london", "remote", "available", "disponible", "it", "qa",
    "network", "security", "cyber", "embedded", "electrical", "mechanical", "civil", "industrial",
    "computer", "informatique", "systems", "systemes", "python", "java",
    "sc", "eng", "tech", "phil", "ed", "ba", "ma", "bs", "ms",          # "M. Sc", "M. Eng"
    # T06: common tech / CV words seen taken as a name in real CVs ("BI Tools", "Spark Streaming", "AWS Certified")
    "tools", "tool", "bi", "api", "apis", "sql", "nosql", "aws", "azure", "gcp", "etl", "elt", "spark", "hadoop",
    "kafka", "airflow", "docker", "kubernetes", "linux", "html", "css", "javascript", "typescript", "react", "angular",
    "node", "django", "flask", "spring", "postgres", "postgresql", "mysql", "mongodb", "oracle", "tableau", "power",
    "excel", "office", "server", "database", "dba", "streaming", "pipeline", "pipelines", "api", "rest", "sms",
    "certified", "certificate", "certification", "award", "conference", "poster", "ieee", "hackathon", "hashcode",
    "statistics", "spss", "talend", "team", "leader", "seasoned", "used", "implemented", "developed", "built",
    "designed", "managed", "created", "worked", "led", "video", "object", "recognition", "detection",
    "classification", "analytics", "analysis", "bank", "ojsc", "llc", "ltd", "inc", "gmbh", "company", "ops",
}

PARTICLES = {"ben", "bin", "ibn", "el", "al", "de", "du", "des", "del", "della", "da", "di", "van", "von",
             "der", "den", "la", "le", "ould", "bou", "abou", "abu", "d'", "dos", "das", "y"}

HONORIFICS = r"(?:Mr|Mrs|Ms|Miss|Mx|Mme|Mlle|Madame|Monsieur|Mademoiselle|Sir|Dame)"


def _norm_line(line: str) -> str:
    line = fold(line)
    line = re.sub(r"[^a-z' ]+", " ", line)
    return re.sub(r"\s+", " ", line).strip()


def header_region(text: str, sections: dict | None = None, max_lines: int = 12, max_chars: int = 700) -> tuple[int, int]:
    """(start, end) of the CV header: the lines before the first section heading.

    The Reader's own split is used when given (sections["header"] / ["contact"])."""
    if sections:
        ends = []
        for key in ("header", "contact"):
            part = (sections.get(key) or "").strip()
            pos = text.find(part[:200]) if part else -1
            if pos >= 0:
                ends.append(pos + len(part))
        if ends:
            return 0, min(max(ends), len(text))
    pos, lines = 0, 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped:
            if _norm_line(stripped) in HEADINGS and lines > 0:
                break
            lines += 1
        pos += len(line)
        if lines >= max_lines or pos >= max_chars:
            break
    return 0, pos


CONTACT_HEADINGS = {"contact", "contacts", "contact information", "contact details", "personal information",
                    "personal details", "personal info", "coordonnees", "informations personnelles",
                    "infos personnelles", "etat civil"}


def private_regions(text: str, sections: dict | None = None) -> list[tuple[int, int]]:
    """The header + every Contact / Personal details section (often at the end of two-column CVs)."""
    regions = [header_region(text, sections)]
    pos, start = 0, None
    for line in text.splitlines(keepends=True):
        norm = _norm_line(line.strip())
        if start is not None and norm in HEADINGS:
            regions.append((start, pos))
            start = None
        if start is None and norm in CONTACT_HEADINGS:
            start = pos
        pos += len(line)
    if start is not None:
        regions.append((start, len(text)))
    return regions


# ------------------------------------------------------------- regex detectors ---

EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.UNICODE)

_TLDS = r"com|net|org|io|dev|me|tn|fr|ai|app|co|xyz|site|tech|info|eu|uk|de|ca|ma|dz|be|ch|online|page|link|blog"
URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s,;|()<>\"']+"
    r"|(?<![\w@.])(?:[a-z0-9-]+\.)+(?:" + _TLDS + r")\b(?:/[^\s,;|()<>\"']*)?",
    re.IGNORECASE,
)
# technology names that look like domains
NOT_URL = {"asp.net", "ado.net", "vb.net", "socket.io", "dot.net", "chart.io", "plotly.io", "pandas.io",
           "ml.net", "f#.net", "openai.com"}
HANDLE_RE = re.compile(r"(?<![\w@.])@[A-Za-z][A-Za-z0-9_.]{2,30}\b")
# "linkedin: /in/jsmith"  "GitHub: jsmith"
PROFILE_LABEL_RE = re.compile(
    r"(?i)\b(?:linkedin|github|gitlab|twitter|x|instagram|facebook|behance|dribbble|kaggle|medium|skype|telegram|whatsapp)"
    # T13: a dash separates a label only with spaces around it ("GitHub - user"): "gitlab-ci" is a tool, not a handle
    r"(?:\s*:\s*|\s+[-–]\s+)(?P<value>[^\s,;|]+)")

PHONE_RE = re.compile(r"(?<![\w+])(?:\+|00)?\(?\d[\d \t().\-/]{6,}\d(?![\w])")
_YEAR_RANGE = re.compile(r"^\(?(?:19|20)\d{2}\)?\s*[-–/ ]\s*\(?(?:19|20)\d{2}\)?$")
_DATE_LIKE = re.compile(r"^\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}$|^\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2}$")
PHONE_LABEL_RE = re.compile(r"(?i)\b(?:tel|t[ée]l[ée]phone|phone|mobile|mob|cell|gsm|portable|whatsapp)\b\.?\s*[:\-]?\s*$")

_MONTHS = (r"jan(?:uary|vier)?|feb(?:ruary)?|f[ée]v(?:rier)?|mar(?:ch|s)?|apr(?:il)?|avr(?:il)?|may|mai|"
           r"june?|juin|july?|juil(?:let)?|aug(?:ust)?|ao[uû]t|sep(?:t(?:ember)?)?|sept(?:embre)?|"
           r"oct(?:ober|obre)?|nov(?:ember|embre)?|dec(?:ember)?|d[ée]c(?:embre)?")
DATE = (r"(?:\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{4}-\d{2}-\d{2}"
        r"|\d{1,2}(?:er|st|nd|rd|th)?\s+(?:" + _MONTHS + r")\.?\s+\d{4}"
        r"|(?:" + _MONTHS + r")\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})")
DOB_RE = re.compile(
    r"(?i)\b(?:born(?:\s+on)?|n[ée]e?\s+le|date\s+of\s+birth|birth\s*date|d\.?o\.?b\.?|date\s+de\s+naissance)"
    r"\s*[:\-]?\s*(?P<value>" + DATE + r")")
AGE_RES = [
    re.compile(r"(?i)(?<![\w.])(?P<value>\d{2}\s*(?:years?|yrs?)[\s-]*old)\b"),
    re.compile(r"(?i)\b(?P<value>[âa]g[ée]e?\s+de\s+\d{2}\s*ans)\b"),
]
# another person named with a title ("Dr. Leila Haddad", "M. Sami Gharbi", "Prof. Martin"): hidden, not stored
TITLED_PERSON_RE = re.compile(
    r"\b(?:Dr|Pr|Prof|Professor|Professeur|Mr|Mrs|Ms|Mme|Mlle|M(?=\.))\.?[ \t]+"
    r"(?P<value>[A-ZÀ-Þ][a-zß-ÿ'’\-]+(?:[ \t]+(?:[A-ZÀ-Þ][a-zß-ÿ'’\-]+|[A-ZÀ-Þ]{2,})){0,2})")
HONORIFIC_RE = re.compile(r"\b(?P<value>" + HONORIFICS + r")\.?(?=\s+[A-ZÀ-Þ])")

# "Label: value" pairs (at the start of a line or after a separator)
_LABELS = {
    "DOB": r"date\s+of\s+birth|birth\s*date|d\.?o\.?b\.?|date\s+de\s+naissance|born|n[ée]e?\s+le",
    "AGE": r"age|[âa]ge",
    "GENDER": r"gender|sex|sexe|genre",
    "NATIONALITY": r"nationality|nationalit[ée]|citizenship|citoyennet[ée]",
    "MARITAL": r"marital\s+status|family\s+status|civil\s+status|situation\s+(?:familiale|matrimoniale)|[ée]tat\s+civil",
    "BIRTHPLACE": r"place\s+of\s+birth|birth\s*place|lieu\s+de\s+naissance",
    "RELIGION": r"religion",
    "ADDRESS": r"(?:home\s+|postal\s+|mailing\s+)?address|adresse(?:\s+postale)?|domicile|r[ée]sidence|lieu\s+de\s+r[ée]sidence",
    "NAME": r"full\s+name|name|nom\s+complet|nom\s+et\s+pr[ée]nom|pr[ée]nom\s+et\s+nom|nom|pr[ée]nom",
}
# only trusted inside the header / contact block (elsewhere "Location:" is a job's city)
_HEADER_ONLY_LABELS = {"LOCATION": r"location|localisation|city|ville|based\s+in"}

_SEP = r"[|•·;]"


def _label_re(pattern: str) -> re.Pattern:
    return re.compile(r"(?im)(?:^|" + _SEP + r")[ \t]*(?:" + pattern + r")[ \t]*[:：\-–][ \t]*"
                      r"(?P<value>[^\n|•·;]*[^\s|•·;])")


LABEL_RES = {kind: _label_re(p) for kind, p in _LABELS.items()}
HEADER_LABEL_RES = {"ADDRESS": _label_re(_HEADER_ONLY_LABELS["LOCATION"])}

STREET_RE = re.compile(
    r"(?i)\b\d{1,5}(?:\s*(?:bis|ter|[a-z]))?,?\s+(?:rue|avenue|av\.?|bd|boulevard|street|st\.?|road|rd\.?|lane|"
    r"impasse|all[ée]e|chemin|route|cit[ée]|place|drive|dr\.?|way|court)\b[^\n|•·;]*")
# "2080 Ariana", "75011 Paris" (same line only; 1950-2035 look like years, so they are skipped)
POSTCODE_CITY_RE = re.compile(r"\b(?!(?:19[5-9]\d|20[0-3]\d)\b)\d{4,5}[ \t]+[A-ZÀ-Þ][\wÀ-ÿ'’\-]+(?:[ \-][A-ZÀ-Þ][\wÀ-ÿ'’\-]+)?")

COUNTRIES = {
    "tunisia", "tunisie", "france", "algeria", "algerie", "morocco", "maroc", "egypt", "egypte", "libya", "libye",
    "germany", "allemagne", "italy", "italie", "spain", "espagne", "portugal", "belgium", "belgique",
    "switzerland", "suisse", "canada", "usa", "united states", "etats-unis", "united kingdom", "uk",
    "royaume-uni", "england", "ireland", "netherlands", "pays-bas", "qatar", "uae", "emirates", "saudi arabia",
    "arabie saoudite", "lebanon", "liban", "jordan", "jordanie", "turkey", "turquie", "india", "inde",
    "china", "chine", "japan", "japon", "senegal", "cameroon", "cameroun", "ivory coast", "cote d'ivoire",
}
NATIONALITY_WORDS = {
    "tunisian", "tunisien", "tunisienne", "french", "francais", "francaise", "algerian", "algerien", "algerienne",
    "moroccan", "marocain", "marocaine", "egyptian", "egyptien", "egyptienne", "libyan", "libyen", "libyenne",
    "german", "allemand", "allemande", "italian", "italien", "italienne", "spanish", "espagnol", "espagnole",
    "belgian", "belge", "swiss", "suisse", "canadian", "canadien", "canadienne", "american", "americain",
    "americaine", "british", "britannique", "senegalese", "senegalais", "senegalaise", "cameroonian",
    "camerounais", "camerounaise", "lebanese", "libanais", "libanaise", "turkish", "turc", "turque",
}
MARITAL_WORDS = {"single", "married", "divorced", "widowed", "celibataire", "marie", "mariee", "divorce",
                 "divorcee", "veuf", "veuve", "pacse", "pacsee"}
GENDER_WORDS = {"male", "female", "homme", "femme", "masculin", "feminin"}


def _spans(regex: re.Pattern, text: str, kind: str, source: str, group: str | int = 0) -> list[Span]:
    out = []
    for m in regex.finditer(text):
        try:
            s, e = m.span(group)
        except IndexError:
            s, e = m.span()
        while e > s and text[e - 1] in " \t,.":
            e -= 1
        if s >= 0 and e > s:
            out.append(Span(s, e, kind, text[s:e], source))
    return out


def find_emails(text: str) -> list[Span]:
    return [Span(sp.start, sp.end, "EMAIL", sp.text.rstrip("."), "regex")
            for sp in _spans(EMAIL_RE, text, "EMAIL", "regex")]


def find_urls(text: str) -> list[Span]:
    out = []
    for m in URL_RE.finditer(text):
        value = m.group(0).rstrip(".,")
        if value.lower() in NOT_URL or "@" in text[max(0, m.start() - 1):m.start()]:
            continue
        out.append(Span(m.start(), m.start() + len(value), "URL", value, "regex"))
    out += _spans(HANDLE_RE, text, "URL", "regex")
    out += [sp for sp in _spans(PROFILE_LABEL_RE, text, "URL", "label", "value")
            if not EMAIL_RE.fullmatch(sp.text)]
    return out


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def find_phones(text: str) -> list[Span]:
    out = []
    for m in PHONE_RE.finditer(text):
        value = m.group(0).strip(" \t.-/")
        if value.startswith("(") and ")" not in value:
            value = value[1:].lstrip()
        if value.endswith(")") and "(" not in value:
            value = value[:-1].rstrip()
        start = m.start() + m.group(0).find(value)
        n = len(_digits(value))
        labelled = bool(PHONE_LABEL_RE.search(text[max(0, start - 20):start]))
        if not 8 <= n <= 15 or _YEAR_RANGE.match(value) or _DATE_LIKE.match(value):
            continue
        # unlabelled runs of 4-digit groups are usually years ("2019 2020 2021")
        if not labelled and not value.startswith(("+", "00")) and (
                re.fullmatch(r"(?:(?:19|20)\d{2}\W*)+", value)
                or len(re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", value)) >= 2 and re.fullmatch(r"[\d/.\-– ]+", value)):
            continue
        out.append(Span(start, start + len(value), "PHONE", value, "regex"))
    return out


def find_proxies(text: str, regions: list[tuple[int, int]]) -> list[Span]:
    """Bias proxies: date of birth, age, gender, honorific, nationality, marital status, birthplace, religion."""
    out = _spans(DOB_RE, text, "DOB", "regex", "value")
    for rx in AGE_RES:
        out += _spans(rx, text, "AGE", "regex", "value")
    out += _spans(HONORIFIC_RE, text, "HONORIFIC", "regex", "value")
    for kind, rx in LABEL_RES.items():
        if kind in ("NAME", "ADDRESS"):
            continue
        out += _spans(rx, text, kind, "label", "value")
    # bare words, trusted only in the header / contact block ("Tunisian, 24 years old, single")
    for h0, h1 in regions:
        for m in re.finditer(r"[^\W\d_][\w'’\-]*", text[h0:h1]):
            word = fold(m.group(0))
            kind = ("NATIONALITY" if word in NATIONALITY_WORDS else "MARITAL" if word in MARITAL_WORDS
                    else "GENDER" if word in GENDER_WORDS else None)
            if kind:
                s = h0 + m.start()
                out.append(Span(s, s + len(m.group(0)), kind, m.group(0), "header"))
    return out


def find_addresses(text: str, regions: list[tuple[int, int]]) -> list[Span]:
    out = _spans(LABEL_RES["ADDRESS"], text, "ADDRESS", "label", "value")
    out += _spans(STREET_RE, text, "ADDRESS", "regex")
    for h0, h1 in regions:
        out += _addresses_in_block(text, h0, h1)
    return out


def _addresses_in_block(text: str, h0: int, h1: int) -> list[Span]:
    out: list[Span] = []
    head = text[h0:h1]
    out += [Span(sp.start + h0, sp.end + h0, sp.kind, sp.text, "label")
            for sp in _spans(HEADER_LABEL_RES["ADDRESS"], head, "ADDRESS", "label", "value")]
    out += [Span(sp.start + h0, sp.end + h0, sp.kind, sp.text, "header")
            for sp in _spans(POSTCODE_CITY_RE, head, "ADDRESS", "header")]
    # "Ariana, Tunisia" / "Lyon, France" as a header segment
    for m in re.finditer(r"[^\n|•·;]+", head):
        seg = m.group(0).strip()
        parts = [p.strip() for p in seg.split(",")]
        if 2 <= len(parts) <= 4 and len(seg) <= 60 and fold(parts[-1]) in COUNTRIES and not any(
                c.isdigit() for c in parts[0][:1]) and "@" not in seg:
            s = h0 + m.start() + m.group(0).find(seg)
            out.append(Span(s, s + len(seg), "ADDRESS", seg, "header"))
    return out


REFERENCE_HEADINGS = {"references", "referees", "references professionnelles", "recommandations", "recommendations"}


def references_region(text: str) -> tuple[int, int] | None:
    """(start, end) of a References section: other people's contacts, hidden but never stored."""
    pos, start = 0, None
    for line in text.splitlines(keepends=True):
        norm = _norm_line(line.strip())
        if start is None and norm in REFERENCE_HEADINGS:
            start = pos
        elif start is not None and norm in HEADINGS:
            return start, pos
        pos += len(line)
    return (start, len(text)) if start is not None else None


# ---------------------------------------------------------------- the name ---

_NAME_TOKEN = re.compile(r"[A-ZÀ-ÖØ-Þ][a-zß-öø-ÿ'’\-]+|[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'’\-]+|[A-ZÀ-Þ]\.")
_WORD = re.compile(r"[^\W\d_][\w'’\-\.]*", re.UNICODE)


def _is_particle(word: str) -> bool:
    return fold(word).strip(".") in PARTICLES


def _name_in_segment(segment: str) -> tuple[int, int] | None:
    """Leading run of 2-4 name-like words: 'JOHN SMITH Data Scientist' -> 'JOHN SMITH'."""
    words = list(_WORD.finditer(segment))
    if not words or segment[:words[0].start()].strip(" \t-–—•·*:"):
        return None
    taken = []
    if re.fullmatch(HONORIFICS + r"\.?", words[0].group(0)):     # "Mme Yasmine Khelifi"
        words = words[1:]
    for w in words:
        token = w.group(0)
        if fold(token).strip(".") in NOT_NAME:
            break
        if _is_particle(token) and taken:
            taken.append(w)
            continue
        if not _NAME_TOKEN.fullmatch(token):
            break
        if taken and segment[taken[-1].end():w.start()].strip():   # "Smith, Data" -> stop at the comma
            break
        taken.append(w)
        if len(taken) == 5:
            break
    while taken and _is_particle(taken[-1].group(0)):
        taken.pop()
    real = [w for w in taken if not _is_particle(w.group(0)) and not w.group(0).endswith(".")]
    if len(real) < 2 or len(taken) > 5:
        return None
    return taken[0].start(), taken[-1].end()


_BULLET_LINE = re.compile(r"[ \t]*[-•*·–—>▪◦●][ \t]")   # T11b: "- Kaggle Notebooks Master"
_LIST_SEP = re.compile(r"[,;/]")                          # T11b: "Classification / Regression / ..."


def find_name(text: str, header: tuple[int, int], emails: list[Span], use_header: bool = True) -> list[Span]:
    """The candidate's name: a 'Name:' label > the header > the email's words."""
    # "Name: John Smith", or French "Prénom : Mohamed Ali" + "Nom : Ben Salah" (all of them are kept)
    labelled = [sp for sp in _spans(LABEL_RES["NAME"], text, "NAME", "label", "value")
                if 1 <= len(sp.text.split()) <= 6 and not any(c.isdigit() for c in sp.text) and "@" not in sp.text]
    if labelled:
        return labelled[:2]

    if not use_header:
        # T11: a CV without section headings still often starts with the bare name ("Fatma Trabelsi"). The T06 fix
        # skipped the header search here (tech words like "BI Tools" were taken as names), so such a name reached the
        # Matcher. Narrow rule: the FIRST non-empty line counts only if the WHOLE line is a name (2-5 name tokens,
        # nothing else). 0 of the 52 base CVs' first lines match it.
        first = re.search(r"[^\n]*\S[^\n]*", text)
        if first:
            line = first.group(0)
            lead = len(line) - len(line.lstrip())
            found = _name_in_segment(line.strip())
            if found and found[0] == 0 and found[1] == len(line.strip()):
                s, e = first.start() + lead, first.start() + lead + found[1]
                return [Span(s, e, "NAME", text[s:e], "header")]

    h0, h1 = header if use_header else (0, 0)  # T06: no header search in a CV without section headings
    head = text[h0:h1]
    for line in re.finditer(r"[^\n]+", head):
        if EMAIL_RE.search(line.group(0)) and len(line.group(0).split()) <= 2:
            continue
        # T11b: a person's name is not an item of a bullet or of a list. Djinni CVs with one heading have most of their
        # text in the "header", and these rules kept taking skills / projects as the name ("- BI tools: Cognos, ...,
        # Qlik Sense, ..."), which then were masked everywhere. Not taken (a skill is never masked "just in case"):
        # a bullet line, and a list item that is not the line's first segment.
        if _BULLET_LINE.match(line.group(0)):
            continue
        is_list = bool(_LIST_SEP.search(line.group(0)))
        # segments: "Curriculum Vitae — Omar Haddad", "JOHN SMITH | Data Scientist", "Nom: X"
        for k, seg in enumerate(re.finditer(r"(?:[^|•·,;/\t:—–\-]|(?<=\w)-(?=\w))+", line.group(0))):
            if is_list and k > 0 and seg.group(0).strip():
                break
            found = _name_in_segment(seg.group(0))
            if found:
                s = h0 + line.start() + seg.start() + found[0]
                e = h0 + line.start() + seg.start() + found[1]
                return [Span(s, e, "NAME", text[s:e], "header")]

    # fallback: capitalised words anywhere that are part of the email ("sarah.connolly@..." -> "Sarah Connolly")
    for email in emails:
        local = fold(email.text.split("@")[0])
        words = [w for w in _WORD.finditer(text)
                 if len(w.group(0)) >= 3 and w.group(0)[0].isupper() and fold(w.group(0)) in local
                 and fold(w.group(0)) not in NOT_NAME]
        for a, b in zip(words, words[1:]):
            if not text[a.end():b.start()].strip():             # two adjacent words: first name + surname
                return [Span(a.start(), b.end(), "NAME", text[a.start():b.end()], "email")]
    return []


def name_parts(name: str) -> list[str]:
    """'Mohamed Ali BEN SALAH' -> ['Mohamed', 'Ali', 'BEN', 'SALAH'] (honorifics and initials dropped)."""
    words = [w.strip(".,") for w in re.split(r"[\s\-]+", name) if w.strip(".,")]
    return [w for w in words if len(w) >= 2 and not re.fullmatch(HONORIFICS, w, re.I)]


# ---------------------------------------------------------------- everything ---

def detect_rules(text: str, sections: dict | None = None) -> list[Span]:
    """All rule-based spans on the original text (not merged yet)."""
    header = header_region(text, sections)
    # T06 fix: a CV without any section heading has no real header block: its first lines are content
    # ("BI Tools: ...", "Spark Streaming ..."), so the header-name rule would take tech words as the name.
    has_headings = bool(sections and set(sections) - {"header", "contact"}) or any(
        _norm_line(line.strip()) in HEADINGS for line in text.splitlines() if line.strip())
    regions = private_regions(text, sections)
    emails = find_emails(text)
    titled = [sp for sp in _spans(TITLED_PERSON_RE, text, "NAME", "titled", "value")
              if fold(sp.text.split()[0]) not in NOT_NAME]
    return (emails + find_urls(text) + find_phones(text) + find_proxies(text, regions)
            + find_addresses(text, regions) + find_name(text, header, emails, use_header=has_headings) + titled)
