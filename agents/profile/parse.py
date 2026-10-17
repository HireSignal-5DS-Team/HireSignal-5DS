"""Step 4 of the Profile Agent: anonymised CV text -> ParsedCV (skills, education, experience).

    anonymised text ─► sections ─► chunks ─► Qwen (one call each) ─► checks + repairs ─► ParsedCV

Only the ANONYMISED text is ever sent to the model. The checks, like the Job Agent's:
- every item's evidence must be a real quote of the anonymised text (else the item is dropped);
- every value (skill name, title, company, school, degree, field) must be written in its evidence;
- no value may contain a placeholder ([NAME] ...);
- dates are normalised by code, not by the model: "06/2020" -> "2020-06", "mars 2019" -> "2019-03",
  "depuis 2022" -> "present"; a date whose year is not in the evidence is dropped;
- duplicates (the same skill in the summary and the skills list) are merged.
Every repair or drop is written in `uncertain`, so a reviewer can see it.
"""

from __future__ import annotations

import re

from agents.job.backend import BackendError
from agents.job.validate import locate_evidence, parse_model_output
from contracts.profile import Education, Experience, ParsedCV, Skill

from .detect import HEADINGS, _norm_line, fold
from .prompts import PROMPT_VERSION, get_prompt

CHUNK_CHARS = 1500
MAX_ATTEMPTS = 2
# sections with no skills / education / experience in them
SKIP_SECTIONS = {"contact", "contacts", "contact information", "contact details", "personal information",
                 "personal details", "coordonnees", "informations personnelles", "references", "referees",
                 "references professionnelles", "interests", "hobbies", "loisirs", "centres d'interet"}
_PLACEHOLDER = re.compile(r"\[(?:NAME|EMAIL|PHONE|URL|ADDRESS|PERSONAL)\]")


# ---------------------------------------------------------------- sections ---

def cv_sections(text: str) -> list[tuple[str, str]]:
    """[(heading as written, body)], header and private sections left out. No heading at all: the whole text."""
    out: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None
    for line in text.splitlines():
        norm = _norm_line(line.strip())
        if line.strip() and norm in HEADINGS:
            current = (line.strip(), [])
            out.append(current)
        elif current is not None:
            current[1].append(line)
    if not out:
        return [("CV", text)]
    return [(h, "\n".join(body).strip()) for h, body in out
            if _norm_line(h) not in SKIP_SECTIONS and "\n".join(body).strip()]


def chunk_sections(sections: list[tuple[str, str]], size: int = CHUNK_CHARS) -> list[str]:
    """Group whole sections up to ~size characters; a longer section is cut at line ends."""
    pieces = []
    for heading, body in sections:
        lines, part = body.splitlines(), []
        for line in lines:
            if part and len("\n".join(part)) + len(line) > size:
                pieces.append(f"Section: {heading}\n" + "\n".join(part))
                part = []
            part.append(line)
        if part:
            pieces.append(f"Section: {heading}\n" + "\n".join(part))
    chunks, current = [], ""
    for piece in pieces:
        if current and len(current) + len(piece) > size:
            chunks.append(current)
            current = ""
        current = f"{current}\n\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks


# ------------------------------------------------------------------- dates ---

_MONTHS = [("janv", 1), ("jan", 1), ("fevr", 2), ("fev", 2), ("feb", 2), ("mars", 3), ("mar", 3),
           ("avr", 4), ("apr", 4), ("mai", 5), ("may", 5), ("juin", 6), ("june", 6), ("jun", 6),
           ("juil", 7), ("july", 7), ("jul", 7), ("aout", 8), ("aug", 8), ("sept", 9), ("sep", 9),
           ("oct", 10), ("nov", 11), ("dec", 12)]
_PRESENT = re.compile(r"\b(present|now|current|currently|today|ongoing|to date|aujourd|actuel|actuellement|"
                      r"en cours|a ce jour|depuis|since)\b")
_DATE_TOKEN = re.compile(r"(?:\d{1,2}[/.\-])?(?:19|20)\d{2}(?:[/.\-]\d{1,2}(?!\d))?|[a-z]{3,9}\.?\s+(?:19|20)\d{2}")


def _month(word: str) -> int | None:
    word = word.strip(".")
    for prefix, number in _MONTHS:
        if word.startswith(prefix):
            return number
    return None


def normalise_date(value, allow_present: bool = True) -> str | None:
    """'06/2020' -> '2020-06', 'mars 2019' -> '2019-03', '2021' -> '2021', 'present' -> 'present'."""
    if value is None:
        return None
    v = fold(str(value)).strip()
    if allow_present and _PRESENT.search(v):          # an end date: "2022 - present", "depuis 2022"
        return "present"
    if m := re.search(r"\b((?:19|20)\d{2})[-/.](\d{1,2})\b", v):
        if 1 <= int(m.group(2)) <= 12:
            return f"{m.group(1)}-{int(m.group(2)):02d}"
    if m := re.search(r"\b(\d{1,2})[-/.]((?:19|20)\d{2})\b", v):
        if 1 <= int(m.group(1)) <= 12:
            return f"{m.group(2)}-{int(m.group(1)):02d}"
    if m := re.search(r"\b([a-z]{3,9})\.?\s+((?:19|20)\d{2})\b", v):
        if (month := _month(m.group(1))) is not None:
            return f"{m.group(2)}-{month:02d}"
    if m := re.search(r"\b((?:19|20)\d{2})\b", v):
        return m.group(1)
    return None


def dates_in(evidence: str) -> list[str]:
    """Normalised dates written in a line, in order: '06/2020 - 09/2020' -> ['2020-06', '2020-09']."""
    out = [normalise_date(m.group(0), allow_present=False) for m in _DATE_TOKEN.finditer(fold(evidence))]
    out = [d for d in out if d]
    if _PRESENT.search(fold(evidence)):
        out.append("present")
    return out


def _date_ok(date: str | None, evidence: str) -> bool:
    if date is None:
        return True
    if date == "present":
        return bool(_PRESENT.search(fold(evidence)))
    return date[:4] in evidence


# ------------------------------------------------------------------ checks ---

def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", fold(s)).strip()


def _value(item: dict, key: str, evidence: str, notes: list[str], where: str) -> str | None:
    v = item.get(key)
    if v is None or not str(v).strip():
        return None
    v = str(v).strip()
    if _PLACEHOLDER.search(v):
        notes.append(f"{where}: {key} contained a placeholder, removed")
        return None
    if _squash(v) not in _squash(evidence):
        notes.append(f"{where}: {key} '{v}' is not written in its evidence, removed")
        return None
    return v


def _evidence(item: dict, text: str, notes: list[str], where: str) -> str | None:
    quote = item.get("evidence")
    if not isinstance(quote, str) or not quote.strip():
        notes.append(f"{where}: no evidence, dropped")
        return None
    found, how = locate_evidence(quote, text)
    if found is None:
        notes.append(f"{where}: evidence not in the CV ({how}), dropped")
    return found


def check_items(data: dict, text: str, notes: list[str]) -> tuple[list[Skill], list[Education], list[Experience]]:
    skills, education, experience = [], [], []

    for item in _list(data, "skills", notes):
        name = str(item.get("name") or "").strip()
        where = f"skill '{name}'"
        ev = _evidence(item, text, notes, where)
        if ev and (name := _value(item, "name", ev, notes, where)):
            skills.append(Skill(name=name.strip(" .,;:"), evidence=ev))

    for item in _list(data, "education", notes):
        where = f"education '{item.get('degree') or item.get('institution')}'"
        ev = _evidence(item, text, notes, where)
        if not ev:
            continue
        fields = {k: _value(item, k, ev, notes, where) for k in ("degree", "field", "institution")}
        end = _date(item.get("end"), ev, notes, where, "end", allow_present=False)
        if end is None and item.get("end") is None and len(set(d[:4] for d in dates_in(ev))) == 1:
            end = dates_in(ev)[-1] if dates_in(ev)[-1] != "present" else None
        if fields["degree"] or fields["institution"]:
            education.append(Education(**fields, end=end, evidence=ev))
        else:
            notes.append(f"{where}: neither degree nor institution, dropped")

    for item in _list(data, "experience", notes):
        where = f"experience '{item.get('title') or item.get('company')}'"
        ev = _evidence(item, text, notes, where)
        if not ev:
            continue
        title = _value(item, "title", ev, notes, where)
        company = _value(item, "company", ev, notes, where)
        start_raw, end_raw = item.get("start"), item.get("end")
        if start_raw and not end_raw and len(dates_in(str(start_raw))) >= 2:   # "2019 – 2023" given as start
            start_raw, end_raw = dates_in(str(start_raw))[:2]
        start = _date(start_raw, ev, notes, where, "start", allow_present=False)
        end = _date(end_raw, ev, notes, where, "end")
        if start is None and end is None and start_raw is None and end_raw is None:
            found = dates_in(ev)
            if len(found) >= 2 and found[0] != "present":
                start, end = found[0], found[1]
                notes.append(f"{where}: dates taken from the evidence")
        if title or company:
            experience.append(Experience(title=title, company=company, start=start, end=end, evidence=ev))
        else:
            notes.append(f"{where}: neither title nor company, dropped")
    return skills, education, experience


def _list(data: dict, key: str, notes: list[str]) -> list[dict]:
    items = data.get(key) or []
    if not isinstance(items, list):
        notes.append(f"'{key}' is not a list, ignored")
        return []
    return [i for i in items if isinstance(i, dict)]


def _date(raw, evidence: str, notes: list[str], where: str, key: str, allow_present: bool = True) -> str | None:
    if raw is None or not str(raw).strip():
        return None
    date = normalise_date(raw, allow_present=allow_present)
    if date is None or not _date_ok(date, evidence):
        notes.append(f"{where}: {key} '{raw}' not found in its evidence, removed")
        return None
    return date


def _dedupe(items: list, key) -> list:
    seen, out = set(), []
    for item in items:
        k = key(item)
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out


# ------------------------------------------------------------------- agent ---

def _ask(backend, chunk: str, system: str, examples: list[dict], notes: list[str], where: str) -> dict | None:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        raw = backend.extract(chunk, system, examples)          # BackendError: server down, no retry
        if (getattr(backend, "last_call", {}) or {}).get("finish_reason") == "length":
            notes.append(f"{where}: answer cut off at the token limit")
        try:
            return parse_model_output(raw)
        except (ValueError, TypeError) as exc:
            notes.append(f"{where}: attempt {attempt}: unreadable answer ({exc})")
    return None


def parse_cv(anon_text: str, cv_id: str, backend, prompt_version: str = PROMPT_VERSION) -> ParsedCV:
    """Anonymised CV text -> ParsedCV. Never give it the original text."""
    system, examples = get_prompt(prompt_version)
    notes: list[str] = []
    skills, education, experience = [], [], []
    chunks = chunk_sections(cv_sections(anon_text))
    for i, chunk in enumerate(chunks, 1):
        data = _ask(backend, chunk, system, examples, notes, f"part {i}/{len(chunks)}")
        if data is None:
            continue
        s, e, x = check_items(data, anon_text, notes)
        skills += s
        education += e
        experience += x
    skills = _dedupe(skills, lambda s: _squash(s.name))
    education = _dedupe(education, lambda e: (_squash(e.degree or ""), _squash(e.institution or ""), e.end))
    experience = _dedupe(experience, lambda x: (_squash(x.title or ""), _squash(x.company or ""), x.start))
    return ParsedCV(candidate_id=cv_id, skills=skills, education=education, experience=experience,
                    uncertain=notes, prompt_version=prompt_version)


__all__ = ["parse_cv", "cv_sections", "chunk_sections", "normalise_date", "dates_in", "check_items",
           "BackendError"]
